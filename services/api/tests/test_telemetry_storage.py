"""Almacenamiento de la telemetría (`app/telemetry/storage.py` y la migración de `telemetry_events`).

- El modelo `TelemetryEvent` sigue siendo el de la fase de captura.
- Mapeo evento → fila (allowlist en `tags`, dimensiones del BRIEFING, timestamps).
- Los eventos del backend (negocio) y los del navegador (técnicos) acaban en la misma tabla por el mismo camino.
- La telemetría del backend nunca rompe una operación de inventario.
- La migración SQL tiene las columnas, índices, permisos y triggers acordados.

Ejecutar desde services/api: uv run pytest tests/test_telemetry_storage.py
"""

import copy
import inspect
import json
import logging
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.telemetry import collector, contract, storage
from app.telemetry.identifiers import client_slug
from app.telemetry.models import TelemetryEvent
from app.telemetry.storage import TelemetryStorageError, telemetry_events, to_row
from tests.conftest import bearer

PSEUDONYM_KEY = "clave-de-seudonimos-de-pruebas-0123456789"
MIGRATION = Path(__file__).resolve().parents[1] / storage.MIGRATION_FILE
SNEAKER = {
    "name": "Zapatilla blanca clásica - Talla 42",
    "sku": "CLT-SNK-W-42",
    "client_name": "PureStep Footwear",
    "category": "fashion",
    "warehouse": "ZGZ",
}


@pytest.fixture(autouse=True)
def telemetry_env(monkeypatch):
    monkeypatch.setenv("TELEMETRY_PSEUDONYM_KEY", PSEUDONYM_KEY)
    monkeypatch.setenv("TELEMETRY_ENVIRONMENT", "test")


@pytest.fixture
def api(make_user):
    return TestClient(app, headers=bearer(make_user("operaciones@trackflow.test")))


def stored_rows() -> list[dict]:
    with storage._engine().connect() as connection:
        return [dict(row) for row in connection.execute(select(telemetry_events)).mappings()]


def example(event_type: str) -> dict:
    event = copy.deepcopy(contract.load_schema()["definitions"][event_type]["examples"][0])
    event["eventId"] = str(uuid.uuid4())
    return event


def register_inbound(api: TestClient, quantity: int = 12):
    sku = api.post("/inventory/products", json=SNEAKER)
    assert sku.status_code == 201, sku.text
    response = api.post(
        "/inventory/orders/inbound", json={"sku_id": sku.json()["id"], "quantity": quantity, "reference": "PO-1"}
    )
    assert response.status_code == 201, response.text
    return response


# --- Modelo -------------------------------------------------------------------------------------------------------


def test_el_modelo_telemetry_event_no_ha_cambiado():
    fields = {name: field.alias for name, field in TelemetryEvent.model_fields.items()}
    assert fields == {
        "event_id": "eventId",
        "timestamp": None,
        "session_id": "sessionId",
        "user_id": "userId",
        "event_type": None,
        "schema_version": "schemaVersion",
        "request_id": "requestId",
        "source": None,
        "environment": None,
        "properties": None,
    }
    assert TelemetryEvent.model_config["extra"] == "forbid"
    assert TelemetryEvent.model_config["frozen"] is True


# --- Mapeo --------------------------------------------------------------------------------------------------------


def test_columnas_de_la_tabla():
    assert [column.name for column in telemetry_events.columns] == [
        "id", "event_type", "timestamp", "service", "tags", "session_id", "user_id", "request_id", "schema_version",
        "environment",
    ]


@pytest.mark.parametrize("event_type", contract.event_types())
def test_cada_ejemplo_del_catalogo_se_convierte_en_fila(event_type):
    event = TelemetryEvent.model_validate(example(event_type))
    row = to_row(event)
    assert row["id"] == uuid.UUID(event.event_id)
    assert row["service"] == event.source
    assert row["tags"] == event.properties
    assert set(row["tags"]) == set(contract.allowed_properties(event_type))
    assert row["timestamp"].tzinfo is not None and row["timestamp"].utcoffset().total_seconds() == 0


def test_tags_solo_copia_la_allowlist():
    # `model_construct` se salta la validación: simula una clave que hubiera llegado hasta aquí.
    valid = TelemetryEvent.model_validate(example("navigation_section_viewed"))
    leaked = TelemetryEvent.model_construct(**{**dict(valid), "properties": {**valid.properties, "email": "a@b.c"}})
    assert "email" not in to_row(leaked)["tags"]
    assert to_row(leaked)["tags"] == valid.properties


def test_timestamp_con_milisegundos_y_microsegundos():
    for text, expected in [
        ("2026-11-10T09:15:42Z", datetime(2026, 11, 10, 9, 15, 42, tzinfo=UTC)),
        ("2026-11-10T09:15:42.318Z", datetime(2026, 11, 10, 9, 15, 42, 318000, tzinfo=UTC)),
        ("2026-11-10T09:15:42.318123Z", datetime(2026, 11, 10, 9, 15, 42, 318123, tzinfo=UTC)),
    ]:
        event = TelemetryEvent.model_validate({**example("navigation_section_viewed"), "timestamp": text})
        assert to_row(event)["timestamp"] == expected


def test_sin_eventos_no_toca_la_base(monkeypatch):
    monkeypatch.setattr("app.telemetry.storage._engine", lambda: pytest.fail("no debe abrir la base"))
    assert storage.insert_events([]) == 0


def test_solo_inserta():
    """Ni el almacenamiento ni el colector tienen sentencias de actualización o borrado."""
    for module in (storage, collector):
        source = inspect.getsource(module)
        assert not re.search(r"\b(update|delete)\s*\(", source)
        assert not re.search(r"\b(UPDATE|DELETE)\b", source)


# --- Mismo mecanismo para negocio (backend) y técnica (navegador) ---------------------------------------------------


def test_orden_de_entrada_se_guarda_con_las_dimensiones_del_briefing(api):
    response = register_inbound(api, quantity=12)
    (row,) = [row for row in stored_rows() if row["event_type"] == "inbound_order_created"]
    assert row["service"] == "backend"
    assert row["environment"] == "test"
    assert row["user_id"].startswith("usr_")
    assert row["tags"] == {
        "warehouse": "zaragoza",
        "client_id": client_slug("PureStep Footwear"),
        "product_id": "CLT-SNK-W-42",
        "product_category": "fashion",
        "quantity": 12,
        "order_id": response.json()["id"],
    }


def test_eventos_tecnicos_y_de_negocio_por_el_mismo_insert(api, monkeypatch):
    calls: list[list[str]] = []
    original = collector.insert_events

    def spy(events):
        calls.append([event.event_type for event in events])
        return original(events)

    monkeypatch.setattr("app.telemetry.collector.insert_events", spy)
    register_inbound(api)
    technical = {**example("frontend_error_captured"), "userId": None}
    assert api.post("/telemetry/events", json={"events": [technical]}).json()["stored"] == 1
    assert ["inbound_order_created"] in calls and ["frontend_error_captured"] in calls
    types = {row["event_type"]: row["service"] for row in stored_rows()}
    assert types["inbound_order_created"] == "backend"
    assert types["frontend_error_captured"] == "frontend"


def test_un_fallo_de_la_base_no_rompe_la_orden(api, monkeypatch, caplog):
    def broken(events):
        raise TelemetryStorageError("OperationalError")

    monkeypatch.setattr("app.telemetry.collector.insert_events", broken)
    caplog.set_level(logging.INFO, logger="trackflow.telemetry")
    register_inbound(api)
    assert "telemetry_batch_store_failed" in caplog.text


def test_con_demasiados_pendientes_se_descarta_sin_bloquear(api, monkeypatch, caplog):
    monkeypatch.setattr("app.telemetry.collector._pending", threading.BoundedSemaphore(1))
    collector._pending.acquire()  # cola llena
    caplog.set_level(logging.WARNING, logger="trackflow.telemetry")
    register_inbound(api)
    assert "storage_queue_full" in caplog.text
    assert [row for row in stored_rows() if row["event_type"] == "inbound_order_created"] == []


def test_el_hilo_de_escritura_guarda_el_evento(api, monkeypatch):
    """Sin el atajo de los tests: el evento se guarda en el hilo `telemetry-writer`, no en el de la petición."""
    threads: list[str] = []
    original = collector.insert_events

    def spy(events):
        threads.append(threading.current_thread().name)
        return original(events)

    monkeypatch.setattr("app.telemetry.collector.insert_events", spy)
    monkeypatch.setattr("app.telemetry.collector.run_in_background", collector._writer.submit)
    register_inbound(api)
    collector._writer.submit(lambda: None).result(timeout=10)  # un solo hilo: espera a lo anterior
    assert threads and all(name.startswith("telemetry-writer") for name in threads)
    assert [row["event_type"] for row in stored_rows()].count("inbound_order_created") == 1


# --- Migración ----------------------------------------------------------------------------------------------------


def test_migracion_columnas_en_el_orden_del_modelo():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = re.search(r"create table if not exists public\.telemetry_events \((.*?)\n\);", sql, re.S).group(1)
    columns = [line.split()[0].strip('"') for line in body.strip().splitlines()]
    assert columns == [column.name for column in telemetry_events.columns]
    assert re.search(r"^\s+tags\s+jsonb\s+not null", body, re.M)
    assert re.search(r"^\s+id\s+uuid\s+primary key", body, re.M)
    assert re.search(r'^\s+"timestamp"\s+timestamptz\s+not null', body, re.M)


def test_migracion_tres_indices():
    sql = MIGRATION.read_text(encoding="utf-8")
    indexes = re.findall(r"create index if not exists (\w+) on public\.telemetry_events using (\w+) \(([^)]+)\)", sql)
    assert sorted(indexes) == [
        ("telemetry_events_event_type_idx", "btree", "event_type"),
        ("telemetry_events_tags_idx", "gin", "tags"),
        ("telemetry_events_timestamp_idx", "btree", '"timestamp"'),
    ]


def test_migracion_permisos_e_inmutabilidad():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "alter table public.telemetry_events enable row level security;" in sql
    assert "revoke all on table public.telemetry_events from public, anon, authenticated, service_role;" in sql
    assert "grant select, insert on table public.telemetry_events to service_role;" in sql
    assert "create policy" not in sql
    assert not re.search(r"grant [^;]*(update|delete|truncate)", sql)
    assert "before update or delete on public.telemetry_events" in sql
    assert "before truncate on public.telemetry_events" in sql
    assert sql.count("begin;") == 1 and sql.strip().endswith("commit;")


def test_migracion_sin_credenciales():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"postgres(ql)?(\+\w+)?://[^<\s\"]+:[^<\s\"]+@", sql)
    assert "password" not in sql.lower() and "service_role_key" not in sql.lower()


def test_resumen_del_log_es_json(api, caplog):
    caplog.set_level(logging.INFO, logger="trackflow.telemetry")
    register_inbound(api)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("telemetry_batch_received"))
    assert json.loads(line.split(" ", 1)[1])["channel"] == "backend"
