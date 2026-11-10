"""Eventos que emite la propia API (fase de captura): métricas obligatorias del BRIEFING, rechazos de órdenes,
login y correlación por petición.

Ejecutar desde services/api: uv run pytest tests/test_telemetry_backend_events.py
"""

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth_models import Role
from app.database import get_engine
from app.inventory_schemas import StockEntryCreate
from app.main import app
from app.services import inventory as inventory_service
from app.services.users import update_user
from app.telemetry.emitter import deterministic_event_id, format_timestamp
from app.telemetry.identifiers import account_ref, client_slug, user_ref
from tests.conftest import PASSWORD, bearer

PSEUDONYM_KEY = "clave-de-seudonimos-de-pruebas-0123456789"
SESSION = "0b7e9c2a-5d4f-4a1b-8c3e-6f9d2a7b1c4e"
SNEAKER = {
    "name": "Zapatilla blanca clásica - Talla 42",
    "sku": "CLT-SNK-W-42",
    "client_name": "PureStep Footwear",
    "category": "fashion",
    "warehouse": "LA",
}


@pytest.fixture(autouse=True)
def telemetry_env(monkeypatch):
    monkeypatch.setenv("TELEMETRY_PSEUDONYM_KEY", PSEUDONYM_KEY)
    monkeypatch.setenv("TELEMETRY_ENVIRONMENT", "test")


@pytest.fixture
def events(monkeypatch):
    """Eventos que el emisor del backend entrega al receptor."""
    delivered: list = []

    def capture(batch, channel):
        assert channel == "backend"
        delivered.extend(batch)
        return len(batch)

    monkeypatch.setattr("app.telemetry.emitter.ingest", capture)
    return delivered


@pytest.fixture
def operator(make_user):
    return make_user("operaciones@trackflow.test")


@pytest.fixture
def api(operator):
    return TestClient(app, headers={**bearer(operator), "X-Session-Id": SESSION})


def of_type(events, event_type):
    return [event for event in events if event.event_type == event_type]


def create_sku(api, **overrides) -> int:
    response = api.post("/inventory/products", json={**SNEAKER, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def inbound(api, sku_id, quantity, **headers):
    return api.post(
        "/inventory/orders/inbound",
        json={"sku_id": sku_id, "quantity": quantity, "reference": "PO-2024-0098"},
        headers=headers,
    )


def outbound(api, sku_id, quantity, exit_type="dispatch"):
    body = {"sku_id": sku_id, "quantity": quantity, "exit_type": exit_type}
    if exit_type == "dispatch":
        body["tracking_number"] = "1Z999AA10123456784"
    return api.post("/inventory/orders/outbound", json=body)


# --- Métricas obligatorias ---------------------------------------------------------------------------------------


class TestInboundOrderCreated:
    def test_tras_registrar_la_entrada(self, api, events, operator):
        sku_id = create_sku(api)
        request_id = str(uuid.uuid4())
        response = inbound(api, sku_id, 120, **{"X-Request-Id": request_id})
        assert response.status_code == 201
        body = response.json()
        (event,) = of_type(events, "inbound_order_created")
        assert event.to_contract() == {
            "eventId": deterministic_event_id("inbound_order_created", body["id"], event.timestamp),
            "timestamp": event.timestamp,
            "sessionId": SESSION,
            "userId": user_ref(operator.id),
            "event_type": "inbound_order_created",
            "schemaVersion": "1.0.0",
            "requestId": request_id,
            "source": "backend",
            "environment": "test",
            "properties": {
                "warehouse": "los_angeles",
                "client_id": "purestep-footwear",
                "product_id": "CLT-SNK-W-42",
                "product_category": "fashion",
                "quantity": 120,
                "order_id": body["id"],
            },
        }
        # El momento del hecho es el `created_at` de la fila, no el del envío.
        assert event.timestamp.startswith(body["created_at"][:19])
        assert response.headers["X-Request-Id"] == request_id

    def test_un_evento_por_orden_y_ninguno_si_se_rechaza(self, api, events):
        sku_id = create_sku(api)
        inbound(api, sku_id, 10)
        inbound(api, sku_id, 5)
        assert inbound(api, 999, 5).status_code == 404
        assert [e.properties["quantity"] for e in of_type(events, "inbound_order_created")] == [10, 5]

    def test_almacen_de_zaragoza_y_sin_datos_del_seed_en_el_usuario(self, api, events, operator):
        sku_id = create_sku(api, sku="GLW-SRM-50", client_name="GlowLab Cosmetics", category="cosmetics", warehouse="ZGZ")
        inbound(api, sku_id, 30)
        (event,) = of_type(events, "inbound_order_created")
        assert event.properties["warehouse"] == "zaragoza"
        assert event.properties["client_id"] == "glowlab-cosmetics"
        assert operator.id not in json.dumps(event.to_contract())


class TestOutboundOrderCreated:
    def test_despacho(self, api, events):
        sku_id = create_sku(api)
        inbound(api, sku_id, 10)
        response = outbound(api, sku_id, 4)
        assert response.status_code == 201
        (event,) = of_type(events, "outbound_order_created")
        assert event.properties == {
            "warehouse": "los_angeles",
            "client_id": "purestep-footwear",
            "product_id": "CLT-SNK-W-42",
            "product_category": "fashion",
            "quantity": 4,
            "order_id": response.json()["id"],
        }
        assert "tracking_number" not in json.dumps(event.to_contract())
        assert "1Z999AA10123456784" not in json.dumps(event.to_contract())

    def test_una_perdida_no_es_un_despacho(self, api, events):
        sku_id = create_sku(api)
        inbound(api, sku_id, 10)
        assert outbound(api, sku_id, 2, "loss").status_code == 201
        assert of_type(events, "outbound_order_created") == []
        (loss,) = of_type(events, "stock_loss_recorded")
        assert loss.properties["quantity"] == 2

    def test_stock_insuficiente_es_un_rechazo_no_un_despacho(self, api, events, operator):
        sku_id = create_sku(api)
        inbound(api, sku_id, 3)
        assert outbound(api, sku_id, 5).status_code == 400
        assert of_type(events, "outbound_order_created") == []
        (rejected,) = of_type(events, "inventory_order_rejected")
        assert rejected.properties == {
            "order_type": "outbound",
            "rejection_reason": "insufficient_stock",
            "warehouse": "los_angeles",
            "client_id": "purestep-footwear",
            "product_id": "CLT-SNK-W-42",
            "product_category": "fashion",
            "quantity": 5,
            "available_quantity": 3,
            "exit_type": "dispatch",
        }
        assert rejected.user_id == user_ref(operator.id)
        assert rejected.request_id is not None

    def test_sku_inexistente(self, api, events):
        assert outbound(api, 4242, 1).status_code == 404
        (rejected,) = of_type(events, "inventory_order_rejected")
        assert rejected.properties["rejection_reason"] == "sku_not_found"
        assert rejected.properties["product_id"] is None


class TestDirectStockEditRejected:
    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_metodo_no_permitido_sobre_un_sku(self, api, events, operator, method):
        sku_id = create_sku(api)
        response = api.request(method, f"/inventory/products/{sku_id}", json={"current_stock": 500})
        assert response.status_code == 405
        (event,) = of_type(events, "direct_stock_edit_rejected")
        assert event.properties == {
            "warehouse": "los_angeles",
            "client_id": "purestep-footwear",
            "product_id": "CLT-SNK-W-42",
            "product_category": "fashion",
            "quantity": 500,
            "attempt_channel": "method_not_allowed",
            "route_template": "/inventory/products/{sku_id}",
            "http_method": method,
            "authenticated": True,
        }
        assert event.user_id == user_ref(operator.id)
        assert event.request_id == response.headers["X-Request-Id"]

    def test_sin_token(self, events):
        response = TestClient(app).put("/inventory/products/1", json={"stock": 3})
        assert response.status_code == 405
        (event,) = of_type(events, "direct_stock_edit_rejected")
        assert event.properties["authenticated"] is False
        assert event.properties["product_id"] is None  # el SKU no existe
        assert event.user_id is None

    @pytest.mark.parametrize("path", ["/inventory/stock", "/inventory/stock/adjust", "/inventory/products/1/stock"])
    def test_ruta_de_stock_inexistente(self, api, events, path):
        response = api.post(path, json={"current_stock": 7})
        assert response.status_code == 404
        (event,) = of_type(events, "direct_stock_edit_rejected")
        assert event.properties["attempt_channel"] == "unknown_stock_route"
        assert event.properties["route_template"] == "unmatched"
        assert event.properties["quantity"] == 7

    def test_campos_de_stock_en_el_alta(self, api, events):
        response = api.post("/inventory/products", json={**SNEAKER, "current_stock": 250})
        assert response.status_code == 201  # la API lo ignora, pero el intento queda registrado
        (event,) = of_type(events, "direct_stock_edit_rejected")
        assert event.properties == {
            "warehouse": "los_angeles",
            "client_id": "purestep-footwear",
            "product_id": "CLT-SNK-W-42",
            "product_category": "fashion",
            "quantity": 250,
            "attempt_channel": "stock_field_in_payload",
            "route_template": "/inventory/products",
            "http_method": "POST",
            "authenticated": True,
        }

    def test_un_alta_normal_o_una_lectura_no_son_intentos(self, api, events):
        sku_id = create_sku(api)
        api.get(f"/inventory/products/{sku_id}")
        api.get("/inventory/stock")
        inbound(api, sku_id, 5)
        assert of_type(events, "direct_stock_edit_rejected") == []


# --- Autenticación -----------------------------------------------------------------------------------------------


class TestLogin:
    def test_login_correcto(self, events, make_user):
        user = make_user("ana@trackflow.test", Role.MANAGER)
        client = TestClient(app, headers={"X-Session-Id": SESSION})
        assert client.post("/auth/login", json={"email": "ana@trackflow.test", "password": PASSWORD}).status_code == 200
        (event,) = of_type(events, "login_succeeded")
        assert event.properties == {"auth_method": "password_json", "user_role": "manager"}
        assert event.user_id == user_ref(user.id)
        assert event.session_id == SESSION  # el sessionId nace en el backoffice antes del login

    def test_credenciales_incorrectas_sin_email_ni_sesion(self, events, make_user):
        make_user("ana@trackflow.test")
        client = TestClient(app, headers={"X-Session-Id": SESSION})
        for email in ("ana@trackflow.test", "nadie@trackflow.test"):
            assert client.post("/auth/login", json={"email": email, "password": "otra-clave-123"}).status_code == 401
        first, second = of_type(events, "login_failed")
        assert first.properties == {
            "failure_reason": "invalid_credentials",
            "auth_method": "password_json",
            "account_ref": account_ref("ana@trackflow.test"),
        }
        assert second.properties["account_ref"] == account_ref("nadie@trackflow.test")
        for event in (first, second):
            assert event.session_id is None and event.user_id is None
            dumped = json.dumps(event.to_contract())
            assert "trackflow.test" not in dumped and "otra-clave" not in dumped

    def test_cuenta_desactivada(self, events, make_user):
        user = make_user("baja@trackflow.test")
        update_user(user.id, {"is_active": False})
        response = TestClient(app).post("/auth/token", data={"username": "baja@trackflow.test", "password": PASSWORD})
        assert response.status_code == 403
        (event,) = of_type(events, "login_failed")
        assert event.properties["failure_reason"] == "account_inactive"
        assert event.properties["auth_method"] == "oauth2_form"
        assert event.user_id == user_ref(user.id)

    def test_datos_no_validos(self, events):
        assert TestClient(app).post("/auth/login", json={"email": "no-es-email"}).status_code == 422
        (event,) = of_type(events, "login_failed")
        assert event.properties == {"failure_reason": "invalid_payload", "auth_method": "password_json", "account_ref": None}


# --- Correlación, procesos internos y robustez -------------------------------------------------------------------


def test_x_request_id_se_genera_si_no_es_un_uuid_v4(api):
    response = api.get("/health", headers={"X-Request-Id": "inventado"})
    assert response.headers["X-Request-Id"] != "inventado"
    assert uuid.UUID(response.headers["X-Request-Id"]).version == 4


def test_cors_admite_las_cabeceras_de_correlacion():
    response = TestClient(app).options(
        "/inventory/orders/inbound",
        headers={
            "Origin": "http://localhost:3002",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-request-id,x-session-id",
        },
    )
    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-request-id" in allowed and "x-session-id" in allowed
    exposed = TestClient(app).get("/health", headers={"Origin": "http://localhost:3002"})
    assert "x-request-id" in exposed.headers["access-control-expose-headers"].lower()


def test_fuera_de_una_peticion_es_un_proceso_interno(events, api, operator):
    """El seed llama a los mismos servicios: sus órdenes salen con `internal_process`, sin sesión ni petición."""
    sku_id = create_sku(api)
    events.clear()
    with Session(get_engine()) as session:
        entry = inventory_service.register_entry(
            session, StockEntryCreate(sku_id=sku_id, quantity=8, reference="SEED"), operator.id
        )
        (event,) = of_type(events, "inbound_order_created")
        assert (event.source, event.session_id, event.request_id) == ("internal_process", None, None)
        assert event.event_id == deterministic_event_id("inbound_order_created", entry.id, format_timestamp(entry.created_at))


def test_sin_clave_de_seudonimos_la_orden_se_registra_y_el_evento_se_descarta(api, events, monkeypatch, caplog):
    sku_id = create_sku(api)
    monkeypatch.delenv("TELEMETRY_PSEUDONYM_KEY")
    caplog.set_level(logging.WARNING, logger="trackflow.telemetry")
    assert inbound(api, sku_id, 5).status_code == 201
    assert of_type(events, "inbound_order_created") == []
    assert "telemetry_event_dropped" in caplog.text
    assert "inbound_order_created" in caplog.text


def test_un_fallo_del_receptor_no_rompe_la_operacion(api, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("receptor caído")

    monkeypatch.setattr("app.telemetry.emitter.ingest", broken)
    sku_id = create_sku(api)
    assert inbound(api, sku_id, 5).status_code == 201
    assert outbound(api, sku_id, 1).status_code == 201
    assert api.put(f"/inventory/products/{sku_id}", json={"current_stock": 9}).status_code == 405


def test_el_receptor_registra_los_eventos_del_backend(api, caplog):
    caplog.set_level(logging.INFO, logger="trackflow.telemetry")
    sku_id = create_sku(api)
    inbound(api, sku_id, 5)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("telemetry_batch_received")]
    summaries = [json.loads(line.split(" ", 1)[1]) for line in lines]
    assert {"channel": "backend", "count": 1, "event_types": ["inbound_order_created"],
            "by_type": {"inbound_order_created": 1}} in summaries


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("PureStep Footwear", "purestep-footwear"),
        ("SoundWave Electronics", "soundwave-electronics"),
        ("GlowLab Cosmetics", "glowlab-cosmetics"),
        ("UrbanThread", "urbanthread"),
        ("  Ñandú & Cía. ", "nandu-cia"),
        ("!!!", "unknown-client"),
    ],
)
def test_client_id_del_plan(name, slug):
    assert client_slug(name) == slug
