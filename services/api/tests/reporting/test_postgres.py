"""Pipeline semanal contra PostgreSQL real (opcional): migraciones, upsert `ON CONFLICT DO UPDATE`, reconciliación con
`tuple NOT IN`, transacción `READ ONLY` y endpoints.

Se salta si no se define `REPORTING_TEST_DATABASE_URL`, que debe apuntar a un PostgreSQL **local y desechable** con
las migraciones `20261110120000_telemetry_events.sql` y `20261113120000_reporting_weekly_performance.sql` aplicadas
(los tests vacían las tablas de `reporting`; `telemetry_events` no se puede vaciar y cada test usa clientes únicos).
Por seguridad solo se aceptan `localhost` y `127.0.0.1`: nunca Supabase.

    $env:REPORTING_TEST_DATABASE_URL = "postgresql+psycopg://postgres:@127.0.0.1:5432/postgres"
    uv run pytest tests/reporting/test_postgres.py
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, select, text
from sqlalchemy.exc import DBAPIError

from app.auth_models import Role
from app.main import app
from data.pipelines import pipeline as flow
from data.pipelines.pipeline import run_weekly_performance
from data.pipelines.weekly_performance.extract import extract_events
from app.reporting.tables import reporting_engine, weekly_performance
from app.reporting.weeks import WeekWindow
from app.telemetry.storage import telemetry_engine
from tests.conftest import bearer
from tests.reporting.helpers import DISCREPANCY, INBOUND, NOW, OUTBOUND, W1, W2, at, event, insert

URL = os.environ.get("REPORTING_TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(not URL, reason="REPORTING_TEST_DATABASE_URL sin definir (PostgreSQL local opcional)")


@pytest.fixture(autouse=True)
def postgres(monkeypatch):
    if make_url(URL).host not in ("localhost", "127.0.0.1"):
        pytest.fail("REPORTING_TEST_DATABASE_URL debe ser un PostgreSQL local y desechable")
    monkeypatch.setenv("DATABASE_URL", URL)
    with reporting_engine().begin() as connection:
        connection.execute(text("truncate reporting.weekly_warehouse_client_performance, reporting.pipeline_runs"))


def client() -> str:
    """Cliente único por test: `telemetry_events` es de solo inserción y conserva los eventos de otros tests."""
    return f"pg-{uuid.uuid4().hex[:12]}"


def rows_of(client_id: str) -> list[dict]:
    with reporting_engine().connect() as connection:
        result = connection.execute(
            select(weekly_performance).where(weekly_performance.c.client_id == client_id).order_by("week_start")
        )
        return [dict(row._mapping) for row in result]


def test_flow_upserts_and_is_idempotent_on_postgres():
    brand = client()
    insert(
        event(INBOUND, at(W1), client_id=brand, quantity=500, order_id=1),
        *(event(OUTBOUND, at(W2, 8 + n), client_id=brand, order_id=100 + n) for n in range(3)),
        event(DISCREPANCY, at(W2), client_id=brand),
    )
    first_run = run_weekly_performance(now=NOW)
    first = rows_of(brand)
    assert [(r["week_start"], r["inbound_units_count"], r["outbound_orders_count"]) for r in first] == [
        (W1, 500, 0),
        (W2, 0, 3),
    ]
    assert first[1]["discrepancy_rate"] == 0.3333 and isinstance(first[1]["discrepancy_rate"], float)
    assert first_run["status"] == "succeeded" and first_run["stats"]["events_read"][INBOUND] >= 1

    insert(event(OUTBOUND, at(W2, 20), client_id=brand, order_id=200))
    run_weekly_performance(now=NOW)
    second = rows_of(brand)
    assert [r["id"] for r in second] == [r["id"] for r in first]  # upsert: mismas filas
    assert second[1]["outbound_orders_count"] == 4 and second[1]["discrepancy_rate"] == 0.25


def test_reconciliation_deletes_rows_that_no_longer_have_events():
    ghost = client()
    with reporting_engine().begin() as connection:
        connection.execute(
            weekly_performance.insert().values(
                id=uuid.uuid4(), warehouse="zaragoza", client_id=ghost, week_start=W2, computed_at=NOW
            )
        )
    run = run_weekly_performance(now=NOW)
    assert rows_of(ghost) == [] and run["rows_deleted"] >= 1


def test_extraction_runs_in_a_read_only_transaction():
    with telemetry_engine().connect() as connection:
        connection = connection.execution_options(postgresql_readonly=True)
        with connection.begin():
            assert connection.execute(text("show transaction_read_only")).scalar() == "on"
            with pytest.raises(DBAPIError) as error:
                connection.execute(text("create temporary table escritura_prohibida (x int)"))
    assert getattr(error.value.orig, "sqlstate", None) == "25006"  # read_only_sql_transaction
    # Y la extracción real funciona en ese modo.
    extract_events(WeekWindow(first=W1, last=W2), "development")


def test_endpoints_on_postgres(make_user, monkeypatch):
    brand = client()
    insert(*(event(OUTBOUND, at(W2), warehouse="zaragoza", client_id=brand, order_id=300 + n) for n in range(2)))
    api = TestClient(app, headers=bearer(make_user("ana@trackflow.test", Role.MANAGER)))
    original = flow.resolve_window
    monkeypatch.setattr(flow, "resolve_window", lambda week_start, weeks, now=None: original(week_start, weeks, NOW))
    assert api.post("/reporting/pipeline-runs").status_code == 201
    body = api.get("/reporting/weekly-warehouse-client-performance").json()
    assert body["week_start"] == W2.isoformat()
    entry = next(e for e in body["entries"] if e["client_id"] == brand)
    assert entry == {
        "warehouse": "zaragoza",
        "client_id": brand,
        "inbound_units_count": 0,
        "outbound_orders_count": 2,
        "stockout_events_count": 0,
        "discrepancy_events_count": 0,
        "discrepancy_rate": 0.0,
    }
    latest = api.get("/reporting/pipeline-runs/latest").json()
    assert latest["status"] == "succeeded" and latest["trigger"] == "api"


def test_partial_unique_index_blocks_a_second_running_run():
    from data.pipelines.pipeline import PipelineAlreadyRunning
    from app.reporting.tables import pipeline_runs

    other = uuid.uuid4()
    with reporting_engine().begin() as connection:
        connection.execute(
            pipeline_runs.insert().values(
                id=other,
                pipeline=flow.PIPELINE_NAME,
                status="running",
                trigger="cli",
                environment="development",
                week_from=W1,
                week_to=W2,
                phase="extracted",
                started_at=NOW.replace(year=2100),  # «reciente»: no se marca como abandonada
            )
        )
    with pytest.raises(PipelineAlreadyRunning):
        run_weekly_performance(now=NOW)
    with reporting_engine().connect() as connection:
        statuses = connection.execute(text("select status, count(*) from reporting.pipeline_runs group by 1")).all()
    assert statuses == [("running", 1)]


def test_rows_point_to_their_run_on_postgres():
    brand = client()
    insert(event(OUTBOUND, at(W2), client_id=brand, order_id=900))
    run = run_weekly_performance(now=NOW)
    (row,) = rows_of(brand)
    assert row["run_id"] == run["id"] and run["phase"] == "loaded"
    assert "capture_coverage" in run["stats"] and "changes" in run["stats"]
