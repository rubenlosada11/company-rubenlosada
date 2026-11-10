"""Receptor temporal `POST /telemetry/events` (fase de captura de telemetría).

Ejecutar desde services/api: uv run pytest tests/test_telemetry_endpoint.py
"""

import copy
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.telemetry import collector, contract
from app.telemetry.identifiers import user_ref
from tests.conftest import bearer

PSEUDONYM_KEY = "clave-de-seudonimos-de-pruebas-0123456789"
ENDPOINT = "/telemetry/events"


@pytest.fixture(autouse=True)
def pseudonym_key(monkeypatch):
    monkeypatch.setenv("TELEMETRY_PSEUDONYM_KEY", PSEUDONYM_KEY)


@pytest.fixture
def api(auth_env):
    return TestClient(app)


@pytest.fixture
def received(monkeypatch):
    """Eventos que llegan al receptor (`collector.ingest`), además de registrarse en el log."""
    batches: list[list] = []
    original = collector.ingest

    def spy(events, channel):
        batches.append(list(events))
        return original(events, channel)

    monkeypatch.setattr("app.routes.telemetry.ingest", spy)
    return batches


def frontend_event(event_type: str = "navigation_section_viewed", **changes) -> dict:
    event = copy.deepcopy(contract.load_schema()["definitions"][event_type]["examples"][0])
    event.update(eventId=str(uuid.uuid4()), userId=None)
    event.update(changes)
    return event


def post(api: TestClient, events, **kwargs):
    return api.post(ENDPOINT, json={"events": events}, **kwargs)


class TestLotesValidos:
    def test_un_evento(self, api, received, caplog):
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        response = post(api, [frontend_event()])
        assert response.status_code == 200
        assert response.json() == {"received": 1}
        line = next(r.getMessage() for r in caplog.records if "telemetry_batch_received" in r.getMessage())
        summary = json.loads(line.split(" ", 1)[1])
        assert summary == {
            "channel": "http",
            "count": 1,
            "event_types": ["navigation_section_viewed"],
            "by_type": {"navigation_section_viewed": 1},
        }

    def test_varios_eventos_de_tipos_distintos(self, api, received, caplog):
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        events = [
            frontend_event(),
            frontend_event("form_started"),
            frontend_event("frontend_error_captured"),
            frontend_event("navigation_section_viewed"),
        ]
        response = post(api, events)
        assert response.json() == {"received": 4}
        assert [event.event_type for event in received[0]] == [
            "navigation_section_viewed", "form_started", "frontend_error_captured", "navigation_section_viewed"
        ]
        assert '"by_type": {"navigation_section_viewed": 2, "form_started": 1, "frontend_error_captured": 1}' in (
            caplog.text
        )

    def test_hasta_50_eventos(self, api):
        assert post(api, [frontend_event() for _ in range(50)]).json() == {"received": 50}

    def test_cuerpo_text_plain_de_send_beacon(self, api, received):
        body = json.dumps({"events": [frontend_event()]})
        response = api.post(ENDPOINT, content=body, headers={"Content-Type": "text/plain;charset=UTF-8"})
        assert response.status_code == 200
        assert len(received) == 1


class TestUserId:
    def test_sin_token_es_nulo_aunque_el_navegador_envie_uno(self, api, received):
        event = frontend_event(userId="usr_" + "a" * 32)
        assert post(api, [event]).status_code == 200
        assert received[0][0].user_id is None

    def test_con_token_valido_es_el_seudonimo_del_usuario(self, api, received, make_user):
        user = make_user("ana@trackflow.test")
        assert post(api, [frontend_event()], headers=bearer(user)).status_code == 200
        assert received[0][0].user_id == user_ref(user.id)
        assert received[0][0].user_id.startswith("usr_")
        assert user.id not in received[0][0].user_id

    def test_con_token_no_valido_se_acepta_el_lote_sin_usuario(self, api, received):
        response = post(api, [frontend_event()], headers={"Authorization": "Bearer no-es-un-jwt"})
        assert response.status_code == 200
        assert received[0][0].user_id is None


class TestLotesNoValidos:
    def test_lote_vacio(self, api, received):
        response = post(api, [])
        assert response.status_code == 422
        assert received == []

    def test_mas_de_50_eventos(self, api):
        assert post(api, [frontend_event() for _ in range(51)]).status_code == 422

    @pytest.mark.parametrize("body", [{}, {"events": {}}, {"eventos": []}, [], "texto"])
    def test_forma_del_cuerpo(self, api, body):
        assert api.post(ENDPOINT, json=body).status_code == 422

    def test_json_mal_formado(self, api):
        response = api.post(ENDPOINT, content='{"events": [', headers={"Content-Type": "application/json"})
        assert response.status_code == 422

    @pytest.mark.parametrize("field", ["eventId", "timestamp", "event_type", "schemaVersion", "sessionId"])
    def test_evento_sin_campo_obligatorio(self, api, field):
        event = frontend_event()
        del event[field]
        response = post(api, [event])
        assert response.status_code == 422
        assert any(field in item["loc"] for item in response.json()["detail"])

    @pytest.mark.parametrize(
        ("field", "value"),
        [("timestamp", 1731230142), ("eventId", 7), ("properties", ["section"]), ("environment", "staging")],
    )
    def test_tipos_incorrectos(self, api, field, value):
        assert post(api, [frontend_event(**{field: value})]).status_code == 422

    @pytest.mark.parametrize(
        "timestamp", ["2026-11-10 18:00:00", "2026-11-10T18:00:00", "2026-11-10T18:00:00+01:00", "2026-02-30T18:00:00Z"]
    )
    def test_timestamp_no_valido(self, api, timestamp):
        assert post(api, [frontend_event(timestamp=timestamp)]).status_code == 422

    @pytest.mark.parametrize(
        "properties",
        [
            {"section": "dashboard", "previous_section": None},  # falta una obligatoria
            {"section": "dashboard", "previous_section": None, "navigation_trigger": "click"},  # enum
            {"section": "/proveedores", "previous_section": None, "navigation_trigger": "initial_load"},  # URL
            {"section": "dashboard", "previous_section": None, "navigation_trigger": "initial_load", "url": "/"},
        ],
    )
    def test_propiedades_mal_formadas(self, api, properties):
        assert post(api, [frontend_event(properties=properties)]).status_code == 422

    def test_un_evento_malo_rechaza_el_lote_entero(self, api, received):
        unknown = {**frontend_event(), "event_type": "page_viewed"}
        response = post(api, [frontend_event(), unknown])
        assert response.status_code == 422
        assert received == []

    def test_solo_eventos_del_frontend(self, api, received):
        backend = frontend_event("inbound_order_created", userId="usr_" + "b" * 32)
        response = post(api, [backend])
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "events", 0, "source"]
        assert received == []

    def test_cuerpo_de_mas_de_64_kb(self, api):
        response = api.post(ENDPOINT, content="x" * (64 * 1024 + 1), headers={"Content-Type": "text/plain"})
        assert response.status_code == 413

    def test_el_422_no_devuelve_los_valores_recibidos(self, api):
        event = frontend_event(properties={"section": "persona@example.com"})
        response = post(api, [event])
        assert response.status_code == 422
        assert "persona@example.com" not in response.text


def test_no_escribe_en_ninguna_base(api, auth_env, inventory_db_url, tmp_path):
    """El stub solo registra: ni TinyDB ni SQLite (ni Supabase, que no se configura en los tests)."""
    assert post(api, [frontend_event() for _ in range(5)]).status_code == 200
    assert not auth_env.exists()
    assert not (tmp_path / "db" / "inventory.db").exists()


def test_publicado_en_openapi(api):
    operation = api.get("/openapi.json").json()["paths"][ENDPOINT]["post"]
    (content,) = operation["responses"]["200"]["content"].values()
    assert content["schema"]["$ref"].endswith("TelemetryBatchAccepted")
    assert "events" in operation["requestBody"]["content"]["application/json"]["schema"]["properties"]
