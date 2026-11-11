"""Receptor `POST /telemetry/events` con almacenamiento: validación individual, lotes mixtos y un único INSERT.

Los tests usan la base SQLite temporal de `conftest.py` (nunca Supabase). Para demostrar que cada lote es una sola
inserción se cuentan las sentencias `INSERT INTO telemetry_events` que llegan a la base y las llamadas a
`insert_events`.

Ejecutar desde services/api: uv run pytest tests/test_telemetry_endpoint.py
"""

import copy
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import get_engine
from app.main import app
from app.telemetry import collector, contract, storage
from app.telemetry.identifiers import user_ref
from app.telemetry.storage import TelemetryStorageError, telemetry_events
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
def inserts(monkeypatch):
    """Llamadas a `insert_events` (cada una con su lote) y sentencias INSERT sobre `telemetry_events` en la base."""
    calls: list[list] = []
    statements: list[dict] = []
    original = collector.insert_events

    def spy(events):
        calls.append(list(events))
        return original(events)

    monkeypatch.setattr("app.telemetry.collector.insert_events", spy)

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO TELEMETRY_EVENTS"):
            statements.append({"executemany": executemany, "values": statement.count("?, ?, ?, ?, ?, ?, ?, ?, ?, ?")})

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", on_execute)
    yield {"calls": calls, "statements": statements}
    event.remove(engine, "before_cursor_execute", on_execute)


def stored_rows() -> list[dict]:
    engine = storage._engine()
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(telemetry_events)).mappings()]


def frontend_event(event_type: str = "navigation_section_viewed", **changes) -> dict:
    event = copy.deepcopy(contract.load_schema()["definitions"][event_type]["examples"][0])
    event.update(eventId=str(uuid.uuid4()), userId=None)
    event.update(changes)
    return event


def invalid_events() -> list[dict]:
    """Elementos que incumplen el contrato de formas distintas."""
    missing_field = frontend_event()
    del missing_field["eventId"]
    return [
        missing_field,
        {**frontend_event(), "event_type": "page_viewed"},  # fuera del catálogo
        frontend_event(properties={"section": "persona@example.com"}),  # allowlist y PII
    ]


def post(api: TestClient, events, **kwargs):
    return api.post(ENDPOINT, json={"events": events}, **kwargs)


# --- Casos 1–4: lotes ---------------------------------------------------------------------------------------------


class TestLotes:
    def test_caso_1_cinco_validos_un_insert(self, api, inserts):
        events = [frontend_event() for _ in range(3)] + [frontend_event("form_started"), frontend_event("form_started")]
        response = post(api, events)
        assert response.status_code == 200
        assert response.json() == {"received": 5, "stored": 5, "rejected": 0}
        assert [len(batch) for batch in inserts["calls"]] == [5]
        assert inserts["statements"] == [{"executemany": False, "values": 5}]
        assert {row["id"] for row in stored_rows()} == {uuid.UUID(item["eventId"]) for item in events}

    def test_caso_2_mixto_tres_validos_y_dos_no_validos(self, api, inserts):
        valid = [frontend_event(), frontend_event("form_started"), frontend_event("frontend_error_captured")]
        events = [valid[0], invalid_events()[0], valid[1], invalid_events()[1], valid[2]]
        response = post(api, events)
        assert response.status_code == 200
        assert response.json() == {"received": 5, "stored": 3, "rejected": 2}
        assert [len(batch) for batch in inserts["calls"]] == [3]
        assert inserts["statements"] == [{"executemany": False, "values": 3}]
        assert sorted(str(row["id"]) for row in stored_rows()) == sorted(item["eventId"] for item in valid)

    def test_caso_3_todos_no_validos_sin_insert(self, api, inserts):
        response = post(api, invalid_events())
        assert response.status_code == 200
        assert response.json() == {"received": 3, "stored": 0, "rejected": 3}
        assert inserts["calls"] == [] and inserts["statements"] == []
        assert stored_rows() == []

    def test_caso_4_lista_vacia(self, api, inserts):
        response = post(api, [])
        assert response.status_code == 200
        assert response.json() == {"received": 0, "stored": 0, "rejected": 0}
        assert inserts["calls"] == [] and inserts["statements"] == []

    def test_hasta_50_eventos_en_un_insert(self, api, inserts):
        response = post(api, [frontend_event() for _ in range(50)])
        assert response.json() == {"received": 50, "stored": 50, "rejected": 0}
        assert inserts["statements"] == [{"executemany": False, "values": 50}]

    @pytest.mark.parametrize("element", [None, 5, "texto", [], {}])
    def test_elementos_que_no_son_eventos_se_rechazan(self, api, element):
        response = post(api, [frontend_event(), element])
        assert response.json() == {"received": 2, "stored": 1, "rejected": 1}

    def test_solo_eventos_del_frontend(self, api):
        backend = frontend_event("inbound_order_created", userId="usr_" + "b" * 32)
        response = post(api, [backend, frontend_event()])
        assert response.json() == {"received": 2, "stored": 1, "rejected": 1}
        assert [row["event_type"] for row in stored_rows()] == ["navigation_section_viewed"]

    def test_reenviar_un_lote_no_duplica_filas(self, api, inserts):
        events = [frontend_event(), frontend_event()]
        assert post(api, events).json() == {"received": 2, "stored": 2, "rejected": 0}
        assert post(api, events).json() == {"received": 2, "stored": 2, "rejected": 0}
        assert len(stored_rows()) == 2
        assert len(inserts["statements"]) == 2

    def test_cuerpo_text_plain_de_send_beacon(self, api):
        body = json.dumps({"events": [frontend_event()]})
        response = api.post(ENDPOINT, content=body, headers={"Content-Type": "text/plain;charset=UTF-8"})
        assert response.status_code == 200
        assert len(stored_rows()) == 1

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("timestamp", 1731230142),
            ("timestamp", "2026-11-10T18:00:00+01:00"),
            ("timestamp", "2026-02-30T18:00:00Z"),
            ("eventId", 7),
            ("properties", ["section"]),
            ("environment", "staging"),
            ("schemaVersion", "2.0.0"),
        ],
    )
    def test_campos_no_validos_se_rechazan_uno_a_uno(self, api, field, value):
        response = post(api, [frontend_event(**{field: value}), frontend_event()])
        assert response.json() == {"received": 2, "stored": 1, "rejected": 1}


# --- Caso 5: envelope -----------------------------------------------------------------------------------------------


class TestEnvelope:
    @pytest.mark.parametrize(
        "body",
        [
            "",  # cuerpo vacío
            '{"events": [',  # JSON mal formado
            "{}",  # sin events
            '{"events": {}}',  # objeto en lugar de lista
            '{"events": null}',  # nulo
            '{"eventos": []}',
            '{"events": [], "extra": 1}',
            "[]",
            '"texto"',
        ],
    )
    def test_caso_5_envelope_incorrecto_422_sin_insert(self, api, inserts, body):
        response = api.post(ENDPOINT, content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"][0] == "body"
        assert inserts["calls"] == [] and inserts["statements"] == []

    def test_mas_de_50_eventos(self, api, inserts):
        response = post(api, [frontend_event() for _ in range(51)])
        assert response.status_code == 422
        assert inserts["calls"] == []

    def test_cuerpo_de_mas_de_64_kb(self, api, inserts):
        response = api.post(ENDPOINT, content="x" * (64 * 1024 + 1), headers={"Content-Type": "text/plain"})
        assert response.status_code == 413
        assert inserts["calls"] == []


# --- Caso 6: fallo de la base ---------------------------------------------------------------------------------------


class TestFalloDeLaBase:
    def test_caso_6_error_de_insert_es_503_sin_cifras(self, api, monkeypatch, caplog):
        def broken(events):
            raise TelemetryStorageError("OperationalError (SQLSTATE 08006)")

        monkeypatch.setattr("app.telemetry.collector.insert_events", broken)
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        response = post(api, [frontend_event(), frontend_event()])
        assert response.status_code == 503
        assert "stored" not in response.text and "received" not in response.text
        assert "telemetry_batch_store_failed" in caplog.text
        assert "telemetry_batch_received" not in caplog.text

    def test_base_inalcanzable_no_revela_credenciales(self, api, monkeypatch, caplog):
        # Puerto 1 de localhost: la conexión se rechaza al momento. La contraseña no debe salir en el log ni en la
        # respuesta.
        # (En Windows el rechazo puede tardar: el timeout de conexión baja a 1 s.)
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://telemetria:clave-secreta-xyz@127.0.0.1:1/postgres")
        monkeypatch.setattr("app.database.POSTGRES_CONNECT_TIMEOUT_SECONDS", 1)
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        response = post(api, [frontend_event()])
        assert response.status_code == 503
        assert "clave-secreta-xyz" not in caplog.text and "clave-secreta-xyz" not in response.text
        assert "127.0.0.1" not in response.text
        line = next(r.getMessage() for r in caplog.records if "telemetry_batch_store_failed" in r.getMessage())
        summary = json.loads(line.split(" ", 1)[1])
        assert summary["count"] == 1
        assert summary["error"] in {"OperationalError", "ConnectionTimeout"}  # psycopg, según el sistema

    def test_si_falla_no_queda_ninguna_fila_del_lote(self, api, monkeypatch):
        # La tercera fila incumple NOT NULL: el INSERT del lote falla entero y no deja las dos primeras.
        events = [frontend_event() for _ in range(3)]

        def failing_statement(engine, rows):
            rows[2]["environment"] = None  # NOT NULL: falla el INSERT entero
            return original(engine, rows)

        original = storage._insert_statement
        monkeypatch.setattr("app.telemetry.storage._insert_statement", failing_statement)
        assert post(api, events).status_code == 503
        assert stored_rows() == []


# --- Caso 7: contrato -----------------------------------------------------------------------------------------------


class TestContrato:
    def test_userId_lo_pone_el_token(self, api, make_user):
        user = make_user("ana@trackflow.test")
        anonymous = frontend_event(userId="usr_" + "a" * 32)
        assert post(api, [anonymous]).status_code == 200
        assert post(api, [frontend_event()], headers=bearer(user)).status_code == 200
        users = sorted((row["user_id"] or "") for row in stored_rows())
        assert users == ["", user_ref(user.id)]
        assert user.id not in users[1]

    def test_token_no_valido_guarda_sin_usuario(self, api):
        response = post(api, [frontend_event()], headers={"Authorization": "Bearer no-es-un-jwt"})
        assert response.status_code == 200
        assert stored_rows()[0]["user_id"] is None

    def test_mapeo_de_columnas(self, api):
        sent = frontend_event(
            "form_submitted", sessionId=str(uuid.uuid4()), requestId=str(uuid.uuid4()), timestamp="2026-11-10T09:15:42.318Z"
        )
        assert post(api, [sent]).json()["stored"] == 1
        (row,) = stored_rows()
        assert row["id"] == uuid.UUID(sent["eventId"])
        assert row["event_type"] == "form_submitted"
        assert row["timestamp"].isoformat().startswith("2026-11-10T09:15:42.318")
        assert row["service"] == "frontend"
        assert row["tags"] == sent["properties"]
        assert row["session_id"] == uuid.UUID(sent["sessionId"])
        assert row["request_id"] == uuid.UUID(sent["requestId"])
        assert row["schema_version"] == sent["schemaVersion"]
        assert row["environment"] == sent["environment"]

    def test_el_log_no_repite_los_valores_rechazados(self, api, caplog):
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        bad = frontend_event(properties={"section": "persona@example.com"})
        response = post(api, [bad])
        assert response.json() == {"received": 1, "stored": 0, "rejected": 1}
        assert "persona@example.com" not in caplog.text
        line = next(r.getMessage() for r in caplog.records if "telemetry_batch_received" in r.getMessage())
        summary = json.loads(line.split(" ", 1)[1])
        assert summary["rejections"][0]["index"] == 0
        assert summary["rejections"][0]["event_type"] == "navigation_section_viewed"
        assert summary["rejections"][0]["reason"] == "schema_validation_failed"

    def test_event_type_desconocido_no_sale_en_el_log(self, api, caplog):
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        post(api, [{**frontend_event(), "event_type": "persona_at_example_com"}])
        assert "persona_at_example_com" not in caplog.text

    def test_resumen_en_el_log(self, api, caplog):
        caplog.set_level(logging.INFO, logger="trackflow.telemetry")
        post(api, [frontend_event(), frontend_event("form_started"), invalid_events()[1]])
        line = next(r.getMessage() for r in caplog.records if "telemetry_batch_received" in r.getMessage())
        summary = json.loads(line.split(" ", 1)[1])
        assert {key: summary[key] for key in ("channel", "received", "stored", "rejected", "duplicates")} == {
            "channel": "http", "received": 3, "stored": 2, "rejected": 1, "duplicates": 0
        }
        assert summary["by_type"] == {"navigation_section_viewed": 1, "form_started": 1}


def test_publicado_en_openapi(api):
    operation = api.get("/openapi.json").json()["paths"][ENDPOINT]["post"]
    (content,) = operation["responses"]["200"]["content"].values()
    assert content["schema"]["$ref"].endswith("TelemetryBatchResult")
    assert {"413", "422", "503"} <= set(operation["responses"])
    assert "events" in operation["requestBody"]["content"]["application/json"]["schema"]["properties"]
