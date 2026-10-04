"""Endpoints del gestor de incidencias: alta y lectura (`POST`/`GET /api/incidents`, `GET /api/incidents/{id}`)."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from analisis_incidencias import gestor
from fastapi.testclient import TestClient

from app.database import incidents_table
from app.incident_models import IncidentRecord
from app.main import app
from app.services import incidents as incidents_service
from app.services.incidents import insert_incident

URL = "/api/incidents"
VALID = {
    "title": "Paquete no localizado en el muelle 3",
    "description": "El paquete figura como recibido pero no aparece en la ubicación asignada.",
    "category": "lost_parcel",
    "origin": "branch",
    "branch": "zaragoza_warehouse",
}
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def errors_by_field(response) -> dict:
    return {item["field"]: item["msg"] for item in response.json()["detail"]}


def store(**changes) -> int:
    """Inserta una incidencia directamente en TinyDB (para fijar estado y fechas)."""
    data = {**VALID, "status": "open", "created_at": BASE, "updated_at": BASE, **changes}
    with incidents_table() as table:
        return insert_incident(table, IncidentRecord.model_validate(data))


@pytest.fixture
def populated(client):
    """Seis incidencias con estados, orígenes, sedes y categorías distintos (ids 1–6, cada una un día más reciente)."""
    rows = [
        ("open", "customer", "la_office", "lost_parcel"),
        ("open", "branch", "zaragoza_warehouse", "inventory_discrepancy"),
        ("in_progress", "branch", "la_warehouse", "warehouse_incident"),
        ("resolved", "customer", "zaragoza_office", "carrier_issue"),
        ("discarded", "internal", "central", "system_failure"),
        ("open", "customer", "la_office", "carrier_issue"),
    ]
    for day, (status, origin, branch, category) in enumerate(rows):
        when = BASE + timedelta(days=day)
        store(status=status, origin=origin, branch=branch, category=category, created_at=when, updated_at=when)
    return client


# --- POST /api/incidents ----------------------------------------------------------------------------------------


def test_create_returns_201_with_server_fields(client, incidents_db_path):
    before = datetime.now(UTC)
    response = client.post(URL, json=VALID)
    assert response.status_code == 201
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    body = response.json()
    assert {key: body[key] for key in VALID} == VALID
    assert body["id"] == 1 and body["status"] == "open"
    assert body["created_at"] == body["updated_at"]
    assert before <= datetime.fromisoformat(body["created_at"]) <= datetime.now(UTC)
    assert set(body) == {*VALID, "id", "status", "created_at", "updated_at"}

    stored = json.loads(incidents_db_path.read_text(encoding="utf-8"))["incidents"]["1"]
    assert stored["status"] == "open" and "source_id" not in stored


def test_create_ignores_server_fields_sent_by_the_client(client):
    payload = {**VALID, "id": 99, "status": "resolved", "created_at": "2020-01-01T00:00:00Z", "source_id": "TRF-1"}
    body = client.post(URL, json=payload).json()
    assert (body["id"], body["status"]) == (1, "open")
    assert body["created_at"].startswith(str(datetime.now(UTC).year))
    assert "source_id" not in body


def test_create_strips_whitespace(client):
    body = client.post(URL, json={**VALID, "title": "  Con espacios  "}).json()
    assert body["title"] == "Con espacios"


@pytest.mark.parametrize("origin", gestor.ORIGENES)
@pytest.mark.parametrize("branch", gestor.SEDES)
def test_create_accepts_every_origin_and_branch(client, origin, branch):
    assert client.post(URL, json={**VALID, "origin": origin, "branch": branch}).status_code == 201


@pytest.mark.parametrize("category", gestor.CATEGORIAS)
def test_create_accepts_every_category(client, category):
    assert client.post(URL, json={**VALID, "category": category}).status_code == 201


@pytest.mark.parametrize("field", list(VALID))
def test_missing_field_is_a_400_that_names_the_field(client, field):
    payload = {key: value for key, value in VALID.items() if key != field}
    response = client.post(URL, json=payload)
    assert response.status_code == 400
    assert errors_by_field(response) == {field: gestor.OBLIGATORIO[field]}
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("field", list(VALID))
@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_field_is_a_400(client, field, value):
    response = client.post(URL, json={**VALID, field: value})
    assert response.status_code == 400
    assert errors_by_field(response) == {field: gestor.OBLIGATORIO[field]}


def test_description_is_required(client):
    response = client.post(URL, json={**VALID, "description": ""})
    assert response.status_code == 400
    assert errors_by_field(response) == {"description": "La descripción es obligatoria."}


@pytest.mark.parametrize(
    ("field", "value"),
    [("category", "LOST_PARCEL"), ("category", "otra"), ("origin", "cliente"), ("branch", "Central"), ("branch", "US")],
)
def test_value_not_allowed_is_a_400_with_the_valid_values(client, field, value):
    response = client.post(URL, json={**VALID, field: value})
    assert response.status_code == 400
    message = errors_by_field(response)[field]
    assert message.startswith(gestor.NO_VALIDO[field])
    assert all(valid in message for valid in gestor.CAMPOS_VALOR[field])


@pytest.mark.parametrize("field", list(VALID))
@pytest.mark.parametrize("value", [123, True, ["a"], {"a": 1}])
def test_wrong_type_is_a_400(client, field, value):
    response = client.post(URL, json={**VALID, field: value})
    assert response.status_code == 400
    assert errors_by_field(response) == {field: f"{gestor.ETIQUETAS[field]} debe ser un texto."}


def test_too_long_values_are_a_400(client):
    response = client.post(URL, json={**VALID, "title": "a" * 121, "description": "b" * 2001})
    assert response.status_code == 400
    assert errors_by_field(response) == {
        "title": "El título no puede superar los 120 caracteres.",
        "description": "La descripción no puede superar los 2000 caracteres.",
    }


def test_several_errors_are_reported_together(client):
    response = client.post(URL, json={"title": "", "category": "x"})
    assert response.status_code == 400
    assert set(errors_by_field(response)) == {"title", "description", "category", "origin", "branch"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{no es json", "El cuerpo de la petición no es un JSON válido."),
        (b"[1, 2]", "El cuerpo de la petición debe ser un objeto JSON."),
        (b'"texto"', "El cuerpo de la petición debe ser un objeto JSON."),
    ],
)
def test_malformed_body_is_a_400(client, content, message):
    response = client.post(URL, content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert [item["msg"] for item in response.json()["detail"]] == [message]


def test_empty_body_is_a_400(client):
    assert client.post(URL).status_code == 400


def test_validation_errors_do_not_echo_the_input_or_internals(client):
    response = client.post(URL, json={**VALID, "category": "valor-secreto-123", "title": 5})
    text = response.text
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert all(set(item) == {"field", "loc", "msg"} for item in response.json()["detail"])
    for leaked in ("valor-secreto-123", "input", "pydantic", "Traceback", "Value error", "Input should"):
        assert leaked not in text


def test_invalid_data_is_not_stored(client):
    client.post(URL, json={**VALID, "branch": ""})
    assert client.get(URL).json() == []


# --- GET /api/incidents -----------------------------------------------------------------------------------------


def test_empty_database_returns_an_empty_list(client, incidents_db_path):
    response = client.get(URL)
    assert (response.status_code, response.json()) == (200, [])


def test_empty_database_with_filters_returns_an_empty_list(client):
    response = client.get(URL, params={"status": "open", "origin": "branch", "branch": "central"})
    assert (response.status_code, response.json()) == (200, [])


def test_list_returns_everything_newest_first(populated):
    body = populated.get(URL).json()
    assert [incident["id"] for incident in body] == [6, 5, 4, 3, 2, 1]
    assert all("source_id" not in incident for incident in body)


def test_same_date_is_ordered_by_id_descending(client):
    for _ in range(3):
        store()
    assert [incident["id"] for incident in client.get(URL).json()] == [3, 2, 1]


@pytest.mark.parametrize(
    ("params", "ids"),
    [
        ({"status": "open"}, [6, 2, 1]),
        ({"status": "in_progress"}, [3]),
        ({"status": "resolved"}, [4]),
        ({"status": "discarded"}, [5]),
        ({"origin": "customer"}, [6, 4, 1]),
        ({"origin": "branch"}, [3, 2]),
        ({"origin": "internal"}, [5]),
        ({"branch": "la_office"}, [6, 1]),
        ({"branch": "central"}, [5]),
        ({"category": "carrier_issue"}, [6, 4]),
        ({"category": "lost_parcel"}, [1]),
        ({"status": "open", "origin": "customer"}, [6, 1]),
        ({"status": "open", "origin": "customer", "branch": "la_office", "category": "carrier_issue"}, [6]),
        ({"status": "resolved", "origin": "branch"}, []),
        ({"category": "other"}, []),
    ],
)
def test_filters(populated, params, ids):
    response = populated.get(URL, params=params)
    assert response.status_code == 200
    assert [incident["id"] for incident in response.json()] == ids


@pytest.mark.parametrize(
    ("param", "value"),
    [("status", "OPEN"), ("status", "cerrada"), ("origin", "x"), ("branch", "US"), ("category", "DAMAGE")],
)
def test_unknown_filter_value_is_a_400(populated, param, value):
    response = populated.get(URL, params={param: value})
    assert response.status_code == 400
    assert errors_by_field(response)[param].startswith(gestor.NO_VALIDO[param])
    assert response.json()["detail"][0]["loc"] == ["query", param]


def test_unknown_query_parameters_are_ignored(populated):
    assert len(populated.get(URL, params={"otro": "x"}).json()) == 6


def test_created_incident_appears_in_the_list(client):
    created = client.post(URL, json=VALID).json()
    assert client.get(URL).json() == [created]
    assert client.get(URL, params={"origin": "branch", "branch": "zaragoza_warehouse"}).json() == [created]


def test_seeded_csv_can_be_listed_and_filtered(client):
    from test_seed_incidents import seed_incidents

    seed_incidents.main([])
    assert len(client.get(URL).json()) == 95
    assert len(client.get(URL, params={"status": "resolved"}).json()) == 52
    assert len(client.get(URL, params={"category": "carrier_issue"}).json()) == 45
    assert len(client.get(URL, params={"origin": "customer"}).json()) == 95
    assert len(client.get(URL, params={"origin": "branch"}).json()) == 0


# --- GET /api/incidents/{id} ------------------------------------------------------------------------------------


def test_get_one(populated):
    response = populated.get(f"{URL}/4")
    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["status"], body["branch"]) == (4, "resolved", "zaragoza_office")


@pytest.mark.parametrize("incident_id", [7, 999, 0, -1])
def test_get_unknown_id_is_a_404(populated, incident_id):
    response = populated.get(f"{URL}/{incident_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": f"Incidencia {incident_id} no encontrada"}


def test_get_on_an_empty_database_is_a_404(client):
    assert client.get(f"{URL}/1").status_code == 404


@pytest.mark.parametrize("incident_id", ["abc", "1.5"])
def test_non_numeric_id_is_a_400(client, incident_id):
    response = client.get(f"{URL}/{incident_id}")
    assert response.status_code == 400
    assert response.json()["detail"][0]["msg"] == "El identificador debe ser un número entero."


# --- Autenticación, 500 y convivencia con el resto de la API ----------------------------------------------------


@pytest.mark.parametrize(("method", "path"), [("post", URL), ("get", URL), ("get", f"{URL}/1")])
def test_requires_authentication(anon_client, method, path):
    response = anon_client.request(method, path, json=VALID if method == "post" else None)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_a_401_not_a_500(anon_client):
    assert anon_client.get(URL, headers={"Authorization": "Bearer no-es-un-token"}).status_code == 401


@pytest.mark.parametrize(
    ("function", "method", "path"),
    [("create_incident", "post", URL), ("list_incidents", "get", URL), ("get_incident", "get", f"{URL}/1")],
)
def test_unexpected_error_is_a_generic_500_without_traceback(client, monkeypatch, caplog, function, method, path):
    def explode(*args, **kwargs):
        raise RuntimeError("detalle interno que no debe salir: C:\\ruta\\secreta")

    monkeypatch.setattr(incidents_service, function, explode)
    with caplog.at_level(logging.ERROR, logger="trackflow.api.incident_manager"):
        response = client.request(method, path, json=VALID if method == "post" else None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Error interno del servidor."}
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert "secreta" not in response.text and "Traceback" not in response.text and "RuntimeError" not in response.text
    assert "detalle interno" in caplog.text  # la traza sí queda en el log del servidor


def test_corrupt_stored_document_is_a_500_not_a_traceback(client):
    with incidents_table() as table:
        table.insert({"title": "sin el resto de campos"})
    response = client.get(URL)
    assert (response.status_code, response.json()) == (500, {"detail": "Error interno del servidor."})


def test_500_from_this_router_keeps_cors_headers(client, monkeypatch):
    monkeypatch.setattr(incidents_service, "list_incidents", lambda **_: 1 / 0)
    response = client.get(URL, headers={"Origin": "http://localhost:3002"})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3002"


def test_global_handler_turns_any_unexpected_error_into_a_generic_500(db_path, make_user, monkeypatch, caplog):
    """Red de seguridad de `main.py`, comprobada en una ruta que no es del gestor."""
    from conftest import bearer

    from app.routes import suppliers

    def explode(*args, **kwargs):
        raise RuntimeError("fallo interno de proveedores")

    monkeypatch.setattr(suppliers, "to_supplier", explode)
    user = make_user("otra@trackflow.test")
    safe_client = TestClient(app, headers=bearer(user), raise_server_exceptions=False)
    created = {
        "name": "X", "country": "Spain", "categories": ["reverse_logistics"], "rate_per_shipment": 1.0,
        "currency": "EUR", "status": "active",
    }
    with caplog.at_level(logging.ERROR, logger="trackflow"):
        response = safe_client.post("/suppliers", json=created)
    assert response.status_code == 500
    assert response.json() == {"detail": "Error interno del servidor."}
    assert "fallo interno" not in response.text
    assert "fallo interno de proveedores" in caplog.text


def test_other_routers_keep_their_422(client):
    assert client.post("/suppliers", json={}).status_code == 422
    assert client.get("/suppliers", params={"country": "France"}).status_code == 422


def test_analyzer_routes_are_not_shadowed(client):
    assert client.get(f"{URL}/results/export").status_code == 404  # sin análisis previo: el 404 del analizador
    assert "analizado" in client.get(f"{URL}/results/export").json()["detail"]
    assert client.post(f"{URL}/analyze").status_code == 400
    assert isinstance(client.post(f"{URL}/analyze").json()["detail"], str)


def test_openapi_documents_the_three_routes():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[f"{URL}/{{incident_id}}"]) == {"get"}
    assert "400" in paths[URL]["post"]["responses"]


# --- PATCH /api/incidents/{id}/status ---------------------------------------------------------------------------

ALLOWED = [("open", "in_progress"), ("open", "discarded"), ("in_progress", "resolved"), ("in_progress", "discarded")]
NOT_ALLOWED = [
    (current, new) for current in gestor.ESTADOS for new in gestor.ESTADOS if (current, new) not in ALLOWED
]


def patch_status(client, incident_id, status):
    return client.patch(f"{URL}/{incident_id}/status", json={"status": status})


def test_there_are_four_allowed_and_twelve_rejected_transitions():
    assert (len(ALLOWED), len(NOT_ALLOWED)) == (4, 12)


@pytest.mark.parametrize(("current", "new"), ALLOWED)
def test_allowed_transition(client, incidents_db_path, current, new):
    incident_id = store(status=current)
    before = datetime.now(UTC)
    response = patch_status(client, incident_id, new)
    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["status"]) == (incident_id, new)
    assert body["created_at"] == "2026-01-01T00:00:00Z"  # no cambia
    assert before <= datetime.fromisoformat(body["updated_at"]) <= datetime.now(UTC)
    assert {key: body[key] for key in VALID} == VALID

    stored = json.loads(incidents_db_path.read_text(encoding="utf-8"))["incidents"][str(incident_id)]
    assert stored["status"] == new and stored["updated_at"] == body["updated_at"]
    assert client.get(f"{URL}/{incident_id}").json() == body


@pytest.mark.parametrize(("current", "new"), NOT_ALLOWED)
def test_rejected_transition_is_a_400_and_changes_nothing(client, incidents_db_path, current, new):
    incident_id = store(status=current)
    before = incidents_db_path.read_bytes()
    response = patch_status(client, incident_id, new)
    assert response.status_code == 400
    assert response.json() == {
        "detail": [{"field": "status", "loc": ["body", "status"], "msg": gestor.validar_transicion(current, new)}]
    }
    assert incidents_db_path.read_bytes() == before


@pytest.mark.parametrize("final", ["resolved", "discarded"])
@pytest.mark.parametrize("new", gestor.ESTADOS)
def test_final_states_cannot_change(client, final, new):
    response = patch_status(client, store(status=final), new)
    assert response.status_code == 400
    assert "estado final" in errors_by_field(response)["status"]


def test_full_lifecycle(client):
    incident_id = client.post(URL, json=VALID).json()["id"]
    assert patch_status(client, incident_id, "in_progress").json()["status"] == "in_progress"
    assert patch_status(client, incident_id, "resolved").json()["status"] == "resolved"
    assert patch_status(client, incident_id, "in_progress").status_code == 400
    assert client.get(f"{URL}/{incident_id}").json()["status"] == "resolved"


@pytest.mark.parametrize("status", ["OPEN", "CLOSED", "cerrada", "", "   ", None, 1, ["open"]])
def test_unknown_status_is_a_400(client, status):
    incident_id = store()
    response = patch_status(client, incident_id, status)
    assert response.status_code == 400
    assert list(errors_by_field(response)) == ["status"]
    assert client.get(f"{URL}/{incident_id}").json()["status"] == "open"


def test_missing_status_is_a_400(client):
    response = client.patch(f"{URL}/{store()}/status", json={})
    assert response.status_code == 400
    assert errors_by_field(response) == {"status": "El estado es obligatorio."}


def test_patch_only_changes_the_status(client):
    incident_id = store()
    body = client.patch(f"{URL}/{incident_id}/status", json={"status": "in_progress", "title": "otro", "id": 9}).json()
    assert (body["id"], body["title"]) == (incident_id, VALID["title"])


@pytest.mark.parametrize("incident_id", [1, 999, 0])
def test_patch_unknown_incident_is_a_404(client, incident_id):
    response = patch_status(client, incident_id, "in_progress")
    assert response.status_code == 404
    assert response.json() == {"detail": f"Incidencia {incident_id} no encontrada"}


def test_patch_unknown_incident_with_invalid_status_is_a_400(client):
    assert patch_status(client, 999, "cerrada").status_code == 400


def test_patch_non_numeric_id_is_a_400(client):
    assert patch_status(client, "abc", "in_progress").status_code == 400


def test_patch_requires_authentication(anon_client):
    store()
    assert patch_status(anon_client, 1, "in_progress").status_code == 401


def test_simultaneous_transitions_from_the_same_state_apply_only_once(client):
    """`open → in_progress` y `open → discarded` a la vez: solo una sale de `open`.

    Si gana `in_progress`, una de las peticiones a `discarded` también es válida después (in_progress → discarded):
    nunca puede haber más de dos cambios aplicados, y el estado final es coherente con ellos.
    """
    incident_id = store()
    targets = ["in_progress", "discarded"] * 4
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda target: patch_status(client, incident_id, target).status_code, targets))
    assert set(codes) <= {200, 400}
    final = client.get(f"{URL}/{incident_id}").json()["status"]
    assert final == "discarded"  # siempre hay una petición a `discarded` que llega con la incidencia aún viva
    assert codes.count(200) in (1, 2)


def test_patch_unexpected_error_is_a_generic_500(client, monkeypatch):
    monkeypatch.setattr(incidents_service, "update_status", lambda *_: 1 / 0)
    response = patch_status(client, store(), "in_progress")
    assert (response.status_code, response.json()) == (500, {"detail": "Error interno del servidor."})


# --- GET /api/incidents/summary ---------------------------------------------------------------------------------

SUMMARY = f"{URL}/summary"


def zeros(values) -> dict:
    return dict.fromkeys(values, 0)


def test_summary_of_an_empty_database_is_all_zeros(client, incidents_db_path):
    response = client.get(SUMMARY)
    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "by_status": zeros(gestor.ESTADOS),
        "by_category": zeros(gestor.CATEGORIAS),
        "by_origin": zeros(gestor.ORIGENES),
        "by_branch": zeros(gestor.SEDES),
    }


def test_summary_with_data(populated):
    assert populated.get(SUMMARY).json() == {
        "total": 6,
        "by_status": {"open": 3, "in_progress": 1, "resolved": 1, "discarded": 1},
        "by_category": {
            **zeros(gestor.CATEGORIAS),
            "lost_parcel": 1, "inventory_discrepancy": 1, "warehouse_incident": 1, "carrier_issue": 2,
            "system_failure": 1,
        },
        "by_origin": {"customer": 3, "branch": 2, "internal": 1},
        "by_branch": {"central": 1, "la_warehouse": 1, "la_office": 2, "zaragoza_warehouse": 1, "zaragoza_office": 1},
    }


def test_every_block_adds_up_to_the_total(populated):
    summary = populated.get(SUMMARY).json()
    for block in ("by_status", "by_category", "by_origin", "by_branch"):
        assert sum(summary[block].values()) == summary["total"]


def test_summary_after_the_seed_matches_the_context(client):
    from test_seed_incidents import seed_incidents

    seed_incidents.main([])
    summary = client.get(SUMMARY).json()
    assert summary["total"] == 95
    assert summary["by_status"] == {"open": 29, "in_progress": 0, "resolved": 52, "discarded": 14}
    assert summary["by_category"] == {
        **zeros(gestor.CATEGORIAS),
        "lost_parcel": 14, "carrier_issue": 45, "delivery_failure": 19, "returns_issue": 17,
    }
    assert summary["by_origin"] == {"customer": 95, "branch": 0, "internal": 0}
    assert summary["by_branch"] == {**zeros(gestor.SEDES), "la_office": 50, "zaragoza_office": 45}


def test_summary_follows_creations_and_status_changes(client):
    incident_id = client.post(URL, json=VALID).json()["id"]
    assert client.get(SUMMARY).json()["by_status"]["open"] == 1
    patch_status(client, incident_id, "in_progress")
    summary = client.get(SUMMARY).json()
    assert (summary["total"], summary["by_status"]["open"], summary["by_status"]["in_progress"]) == (1, 0, 1)
    assert summary["by_branch"]["zaragoza_warehouse"] == 1


def test_summary_is_not_read_as_an_incident_id(client):
    response = client.get(SUMMARY)
    assert response.status_code == 200 and "total" in response.json()


def test_summary_requires_authentication(anon_client):
    assert anon_client.get(SUMMARY).status_code == 401


def test_summary_unexpected_error_is_a_generic_500(client, monkeypatch):
    monkeypatch.setattr(incidents_service, "summarize", lambda: 1 / 0)
    response = client.get(SUMMARY)
    assert (response.status_code, response.json()) == (500, {"detail": "Error interno del servidor."})


def test_openapi_documents_patch_and_summary():
    paths = app.openapi()["paths"]
    assert set(paths[SUMMARY]) == {"get"}
    assert set(paths[f"{URL}/{{incident_id}}/status"]) == {"patch"}


def test_status_change_is_validated_by_the_model_before_writing(client, incidents_db_path, monkeypatch):
    """Un `updated_at` anterior a `created_at` (reloj atrasado) no llega a la base: 500 genérico y nada cambia."""
    incident_id = store(created_at=BASE, updated_at=BASE)
    before = incidents_db_path.read_bytes()
    monkeypatch.setattr(incidents_service, "utc_now", lambda: BASE - timedelta(days=1))
    response = patch_status(client, incident_id, "in_progress")
    assert (response.status_code, response.json()) == (500, {"detail": "Error interno del servidor."})
    assert incidents_db_path.read_bytes() == before
