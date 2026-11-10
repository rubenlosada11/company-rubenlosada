"""Contratos de serialización de la API (auditoría de serialización, `docs/serialization-audit.md`).

Comprueban en ejecución que:

- toda ruta con cuerpo JSON declara un `response_model` explícito y OpenAPI lo publica;
- ninguna respuesta lleva contraseñas, hashes, tokens de recuperación ni campos internos;
- registro, login y recuperación de contraseña no devuelven el email (solo `GET /auth/me`), y la recuperación no
  revela si un email está registrado;
- cada recurso devuelve exactamente los campos de su esquema (ni uno más) y los esquemas de entrada no aceptan campos
  protegidos.

Ejecutar desde services/api: uv run pytest tests/test_serialization.py
"""

import csv
import inspect
import io
import json
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.analysis_schemas import ResultadoAnalisis
from app.auth_models import Role
from app.database import incidents_table, suppliers_table
from app.incident_models import Incident, IncidentRecord, IncidentStatus
from app.inventory_schemas import SKURead, SKUSummary, StockEntryRead, StockExitRead
from app.main import app
from app.models import Supplier
from app.routes import auth, incident_manager, incidents, inventory, profiles, suppliers, telemetry, users
from app.services import incidents as incidents_service
from app.services import password_reset as password_reset_service
from app.services import users as users_service
from tests.conftest import PASSWORD, bearer
from tests.test_incidents import CSV_REAL

# Nombres de campo que nunca pueden aparecer en una respuesta (en ningún nivel de anidamiento).
FORBIDDEN_KEYS = {
    "password",
    "hashed_password",
    "new_password",
    "current_password",
    "password_changed_at",
    "token",
    "token_hash",
    "reset_token",
    "invitation_code",
    "source_id",
    "customer_email",
    "secret_key",
}

# Rutas sin cuerpo JSON: no llevan `response_model` (ver la sección 12.5 de la auditoría).
NO_JSON_BODY = {
    ("DELETE", "/users/{user_id}"),
    ("DELETE", "/suppliers/{supplier_id}"),
    ("GET", "/api/incidents/results/export"),
}

ROUTERS = [auth, users, profiles, suppliers, incidents, incident_manager, inventory, telemetry]


def all_keys(value) -> set[str]:
    """Todas las claves de un JSON, a cualquier profundidad."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in all_keys(item)}
    return set()


def assert_no_sensitive_keys(body) -> None:
    leaked = all_keys(body) & FORBIDDEN_KEYS
    assert not leaked, f"La respuesta expone campos sensibles: {sorted(leaked)}"


def fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields)


def application_routes() -> list[APIRoute]:
    """Rutas de los routers de `app/routes/` más `/health` (las internas de FastAPI no cuentan)."""
    routes = [route for module in ROUTERS for route in module.router.routes]
    routes += [route for route in app.routes if isinstance(route, APIRoute)]
    return routes


def operations(route: APIRoute) -> set[tuple[str, str]]:
    prefix = next((module.router.prefix for module in ROUTERS if route in module.router.routes), "")
    path = route.path if route.path.startswith(prefix) else prefix + route.path
    return {(method, path) for method in route.methods}


# --- Contratos de todas las rutas ----------------------------------------------------------------------------------


def test_route_inventory_matches_the_registered_app():
    """Los routers revisados son todos los que publica la app: no queda ninguna ruta fuera de la auditoría."""
    declared = {operation for route in application_routes() for operation in operations(route)}
    published = {
        (method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item
    }
    assert declared == published
    # 33 de la auditoría + `POST /telemetry/events` (captura de telemetría).
    assert len(declared) == 34


@pytest.mark.parametrize("route", application_routes(), ids=lambda route: f"{sorted(route.methods)[0]} {route.path}")
def test_every_json_route_declares_an_explicit_response_model(route):
    if operations(route) & NO_JSON_BODY:
        return
    decorator = inspect.getsource(route.endpoint).split("def ", 1)[0]
    assert "response_model=" in decorator, "El decorador debe declarar response_model (no basta la anotación)"
    model = route.response_model
    inner = model.__args__[0] if getattr(model, "__origin__", None) is list else model
    # `Movement` es una unión discriminada de dos modelos: también es un contrato cerrado.
    members = getattr(getattr(inner, "__origin__", None), "__args__", None) or getattr(inner, "__args__", None)
    candidates = [inner] if isinstance(inner, type) else list(members or [])
    assert candidates and all(isinstance(c, type) and issubclass(c, BaseModel) for c in candidates), model


def test_openapi_documents_every_json_response_with_a_named_schema():
    for path, item in app.openapi()["paths"].items():
        for method, operation in item.items():
            if (method.upper(), path) in NO_JSON_BODY:
                continue
            ok = next(code for code in operation["responses"] if code.startswith("2"))
            schema = next(iter(operation["responses"][ok]["content"].values()))["schema"]
            schema = schema.get("items", schema)
            assert "$ref" in schema or "oneOf" in schema, f"{method.upper()} {path}: {schema}"


def test_openapi_documents_the_csv_download_as_csv_and_has_unique_schema_names():
    spec = app.openapi()
    export = spec["paths"]["/api/incidents/results/export"]["get"]["responses"]["200"]["content"]
    assert list(export) == ["text/csv"]
    assert not [name for name in spec["components"]["schemas"] if name.startswith("app__")]
    assert {"SupplierCategory", "ProductCategory", "RegisterResponse", "ResultadoAnalisis"} <= set(
        spec["components"]["schemas"]
    )


# --- Autenticación -------------------------------------------------------------------------------------------------

NEW_USER = {"email": "Laura.Gomez@TrackFlow.test", "password": "contraseña-segura", "name": "Laura Gómez"}
TOKEN_FIELDS = {"access_token", "token_type", "expires_in"}
PROFILE_FIELDS = {"id", "user_id", "name", "phone", "address"}


@pytest.fixture
def ana(make_user):
    return make_user("ana@trackflow.test", name="Ana Whitfield", phone="+1 213 555 0100")


def test_register_returns_the_account_without_email_or_credentials(anon_client):
    response = anon_client.post("/users", json={**NEW_USER, "invitation_code": "no-se-guarda-ni-se-devuelve"})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "role", "is_active", "created_at", "profile"}
    assert set(body["profile"]) == PROFILE_FIELDS
    assert "laura.gomez@trackflow.test" not in response.text.lower()
    assert "contraseña-segura" not in response.text
    assert_no_sensitive_keys(body)


@pytest.mark.parametrize("route", ["/auth/login", "/auth/token"])
def test_login_returns_only_the_access_token(anon_client, ana, route):
    if route == "/auth/login":
        response = anon_client.post(route, json={"email": ana.email, "password": PASSWORD})
    else:
        response = anon_client.post(route, data={"username": ana.email, "password": PASSWORD})
    assert response.status_code == 200
    assert set(response.json()) == TOKEN_FIELDS
    assert ana.email not in response.text
    assert_no_sensitive_keys(response.json())


def test_forgot_password_gives_the_same_answer_whether_or_not_the_email_exists(anon_client, ana, make_user):
    inactive = make_user("inactiva@trackflow.test")
    users_service.update_user(inactive.id, {"is_active": False})

    answers = [
        anon_client.post("/auth/forgot-password", json={"email": email})
        for email in (ana.email, "nadie@trackflow.test", inactive.email)
    ]
    assert {response.status_code for response in answers} == {200}
    assert len({response.content for response in answers}) == 1  # mismo cuerpo, byte a byte
    body = answers[0].json()
    assert set(body) == {"message"} and ana.email not in answers[0].text
    assert_no_sensitive_keys(body)


def test_reset_password_confirms_without_sensitive_data(anon_client, ana):
    issued = password_reset_service.issue_reset_token(ana.id)
    response = anon_client.post("/auth/reset-password", json={"token": issued.token, "new_password": "otra-segura-1"})
    assert response.status_code == 200
    assert set(response.json()) == {"message"}
    assert issued.token not in response.text and ana.email not in response.text

    reused = anon_client.post("/auth/reset-password", json={"token": issued.token, "new_password": "otra-segura-2"})
    assert reused.status_code == 400 and set(reused.json()) == {"detail"} and issued.token not in reused.text


def test_change_password_returns_only_a_new_token(anon_client, ana):
    response = anon_client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "nueva-contraseña-1"},
        headers=bearer(ana),
    )
    assert response.status_code == 200
    assert set(response.json()) == TOKEN_FIELDS
    assert_no_sensitive_keys(response.json())


def test_me_returns_the_email_and_never_the_session_control_fields(anon_client, ana):
    # Tras un cambio de contraseña el usuario guarda `password_changed_at`: tampoco debe salir.
    users_service.change_password(ana.id, ana.hashed_password)
    headers = {"Authorization": "Bearer " + anon_client.post(
        "/auth/login", json={"email": ana.email, "password": PASSWORD}
    ).json()["access_token"]}

    body = anon_client.get("/auth/me", headers=headers).json()
    assert set(body) == {"id", "email", "role", "is_active", "created_at", "profile"}
    assert body["email"] == ana.email
    assert set(body["profile"]) == PROFILE_FIELDS and body["profile"]["name"] == "Ana Whitfield"
    assert_no_sensitive_keys(body)


def test_user_administration_and_profile_responses_are_whitelisted(anon_client, make_user, ana):
    admin = make_user("admin@trackflow.test", Role.ADMIN)
    users_service.change_password(ana.id, ana.hashed_password)
    headers = bearer(admin)

    listed = anon_client.get("/users", headers=headers).json()
    assert len(listed) == 2 and all(set(user) == {"id", "email", "role", "is_active", "created_at"} for user in listed)
    detail = anon_client.get(f"/users/{ana.id}", headers=headers).json()
    updated = anon_client.put(f"/users/{ana.id}", json={"role": "manager"}, headers=headers).json()
    profile = anon_client.get("/profiles/me", headers=bearer(ana)).json()

    assert set(detail) == set(updated) == {"id", "email", "role", "is_active", "created_at"}
    assert set(profile) == PROFILE_FIELDS
    for body in (listed, detail, updated, profile):
        assert_no_sensitive_keys(body)


# --- Entrada: campos protegidos y PATCH/PUT parciales --------------------------------------------------------------


@pytest.mark.parametrize("extra", [{"hashed_password": "$2b$12$x"}, {"created_at": "2020-01-01T00:00:00Z"}])
def test_register_rejects_protected_fields(anon_client, extra):
    response = anon_client.post("/users", json={**NEW_USER, **extra})
    assert response.status_code == 422
    assert users_service.get_user_by_email("laura.gomez@trackflow.test") is None


@pytest.mark.parametrize(
    "extra", [{"password": "otra-segura-1"}, {"hashed_password": "$2b$12$x"}, {"id": "otro"}, {"created_at": "x"}]
)
def test_user_update_rejects_fields_outside_its_schema(anon_client, ana, extra):
    response = anon_client.put(f"/users/{ana.id}", json={"is_active": True, **extra}, headers=bearer(ana))
    assert response.status_code == 422
    assert "otra-segura-1" not in response.text  # el 422 no repite los valores recibidos


def test_profile_update_distinguishes_omitted_fields_from_null(anon_client, ana):
    headers = bearer(ana)
    only_name = anon_client.put("/profiles/me", json={"name": "Ana W."}, headers=headers).json()
    assert (only_name["name"], only_name["phone"]) == ("Ana W.", "+1 213 555 0100")  # omitido: no cambia

    cleared = anon_client.put("/profiles/me", json={"phone": None}, headers=headers).json()
    assert (cleared["name"], cleared["phone"]) == ("Ana W.", None)  # null: se vacía


def test_user_update_rejects_null_instead_of_clearing(anon_client, make_user):
    admin = make_user("admin@trackflow.test", Role.ADMIN)
    response = anon_client.put(f"/users/{admin.id}", json={"role": None}, headers=bearer(admin))
    assert response.status_code == 422


# --- Recursos ------------------------------------------------------------------------------------------------------

SUPPLIER = {
    "name": "Proveedor de pruebas",
    "country": "Spain",
    "categories": ["carrier_last_mile"],
    "rate_per_shipment": 4.5,
    "currency": "EUR",
    "status": "active",
}


def test_supplier_responses_have_exactly_the_supplier_fields_and_ignore_server_fields(client):
    created = client.post("/suppliers", json={**SUPPLIER, "id": 999, "updated_at": "2000-01-01T00:00:00Z"})
    assert created.status_code == 201
    body = created.json()
    assert set(body) == fields(Supplier)
    assert body["id"] != 999 and not body["updated_at"].startswith("2000")  # los pone el servidor

    listed = client.get("/suppliers").json()
    assert [set(item) for item in listed] == [fields(Supplier)]


def test_a_stored_supplier_that_breaks_an_input_rule_does_not_break_the_list(client):
    """La salida ya no repite las reglas de entrada: un dato antiguo o editado a mano no convierte el listado en 500."""
    with suppliers_table() as table:
        table.insert({**SUPPLIER, "currency": "USD", "updated_at": datetime.now(UTC).isoformat()})
    response = client.get("/suppliers")
    assert response.status_code == 200 and response.json()[0]["currency"] == "USD"


INCIDENT = {
    "title": "Paquete perdido en ruta",
    "description": "El cliente no ha recibido el paquete.",
    "category": "lost_parcel",
    "origin": "customer",
    "branch": "central",
}


def test_incident_responses_hide_the_internal_source_id_and_ignore_server_fields(client):
    created = client.post(
        "/api/incidents", json={**INCIDENT, "id": 50, "status": "resolved", "created_at": "2000-01-01T00:00:00Z"}
    )
    assert created.status_code == 201
    assert set(created.json()) == fields(Incident)
    assert created.json()["status"] == "open" and created.json()["id"] != 50

    now = datetime.now(UTC)
    with incidents_table() as table:
        incidents_service.insert_incident(
            table,
            IncidentRecord(
                **INCIDENT, status=IncidentStatus.OPEN, created_at=now, updated_at=now, source_id="TRF-000123"
            ),
        )
    listed = client.get("/api/incidents")
    assert [set(item) for item in listed.json()] == [fields(Incident)] * 2
    assert "TRF-000123" not in listed.text
    detail = client.get(f"/api/incidents/{listed.json()[0]['id']}").json()
    assert set(detail) == fields(Incident)


def test_inventory_responses_and_movement_projection(client):
    sku = client.post(
        "/inventory/products",
        json={"name": "Sérum", "sku": "SER-01", "client_name": "Lumière", "category": "cosmetics", "warehouse": "ZGZ"},
    ).json()
    assert set(sku) == fields(SKURead)

    entry = client.post(
        "/inventory/orders/inbound",
        json={"sku_id": sku["id"], "quantity": 5, "reference": "PO-1", "user_uuid": "otro-usuario", "id": 77},
    ).json()
    exit_ = client.post(
        "/inventory/orders/outbound", json={"sku_id": sku["id"], "quantity": 2, "exit_type": "loss"}
    ).json()
    assert set(entry) == fields(StockEntryRead) and set(exit_) == fields(StockExitRead)
    assert entry["user_uuid"] != "otro-usuario" and entry["id"] != 77  # los pone el servidor

    movements = client.get("/inventory/orders").json()
    assert [m["movement_type"] for m in movements] == ["outbound", "inbound"]
    assert set(movements[0]) == fields(StockExitRead) | {"movement_type", "sku"}
    assert set(movements[1]) == fields(StockEntryRead) | {"movement_type", "sku"}
    # Proyección plana del SKU: sin stock ni movimientos anidados.
    assert all(set(m["sku"]) == fields(SKUSummary) for m in movements)
    assert "current_stock" not in movements[0]["sku"]


def test_health_has_its_own_schema(anon_client):
    assert anon_client.get("/health").json() == {"status": "ok"}


# --- Analizador ----------------------------------------------------------------------------------------------------


@pytest.fixture
def no_previous_analysis():
    app.state.ultimo_analisis = None
    yield
    app.state.ultimo_analisis = None


def upload(client, content: bytes):
    return client.post("/api/incidents/analyze", files={"file": ("incidents.csv", content, "text/csv")})


def test_analysis_response_matches_its_schema_and_has_no_customer_emails(client, no_previous_analysis):
    content = CSV_REAL.read_bytes()
    response = upload(client, content)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == fields(ResultadoAnalisis)
    ResultadoAnalisis.model_validate(body)
    rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    emails = {row["customer_email"] for row in rows if "@" in (row["customer_email"] or "")}
    assert emails and not any(email in response.text for email in emails)
    assert_no_sensitive_keys(body)


def test_a_new_key_from_the_package_does_not_reach_the_client(client, monkeypatch, no_previous_analysis):
    real = incidents.analizar
    monkeypatch.setattr(incidents, "analizar", lambda *args: {**real(*args), "customer_email": ["x@example.com"]})
    response = upload(client, CSV_REAL.read_bytes())
    assert response.status_code == 200
    assert "customer_email" not in response.json() and "x@example.com" not in response.text


def test_a_result_that_breaks_the_contract_gives_a_generic_500_and_keeps_the_last_analysis(
    client, monkeypatch, no_previous_analysis
):
    assert upload(client, CSV_REAL.read_bytes()).status_code == 200
    previous = app.state.ultimo_analisis

    monkeypatch.setattr(incidents, "analizar", lambda *args: {"archivo": "roto.csv"})
    response = upload(client, CSV_REAL.read_bytes())
    assert response.status_code == 500 and response.json() == {"detail": "Error interno del servidor."}
    assert app.state.ultimo_analisis is previous
    export = client.get("/api/incidents/results/export")
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")


def test_no_response_in_a_full_session_contains_a_password_or_hash(anon_client, make_user):
    """Recorrido completo con la misma cuenta: ninguna respuesta repite la contraseña ni el hash bcrypt."""
    registered = anon_client.post("/users", json=NEW_USER)
    stored = users_service.get_user_by_email("laura.gomez@trackflow.test")
    token = anon_client.post("/auth/login", json=NEW_USER).json()["access_token"]
    api = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    responses = [registered, api.get("/auth/me"), api.get("/profiles/me"), api.get(f"/users/{stored.id}")]
    for response in responses:
        assert response.status_code in (200, 201)
        assert NEW_USER["password"] not in response.text
        assert stored.hashed_password not in response.text
        assert_no_sensitive_keys(json.loads(response.text))
