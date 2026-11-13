"""Flow completo y registro de ejecuciones (`app/reporting/flow.py` y `runs.py`, PIPELINE_DESIGN.md §5, §7–§9).

Idempotencia, autorreparación, ejecuciones fallidas y abandonadas, concurrencia, solo lectura del origen y la línea de
comandos (`python -m app.reporting`).

Ejecutar desde services/api: uv run pytest tests/reporting/test_flow.py
"""

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.reporting import __main__ as cli
from app.reporting import flow, runs
from app.reporting.flow import (
    PIPELINE_NAME,
    PipelineAlreadyRunning,
    PipelineRunFailed,
    compute_weekly_performance,
    run_weekly_performance,
)
from app.reporting.tables import ReportingStorageError, pipeline_runs, reporting_engine, weekly_performance
from app.reporting.weeks import WeekWindow, WindowError
from tests.reporting.helpers import (
    DISCREPANCY,
    INBOUND,
    NOW,
    OUTBOUND,
    STOCKOUT,
    W1,
    W2,
    at,
    event,
    insert,
    telemetry_count,
)


def report_rows() -> list[dict]:
    with reporting_engine().connect() as connection:
        rows = connection.execute(select(weekly_performance).order_by("week_start", "warehouse", "client_id")).all()
    return [dict(row._mapping) for row in rows]


def kpis(rows: list[dict]) -> list[tuple]:
    return [
        (
            r["warehouse"],
            r["client_id"],
            r["week_start"],
            r["inbound_units_count"],
            r["outbound_orders_count"],
            r["stockout_events_count"],
            r["discrepancy_events_count"],
            r["discrepancy_rate"],
        )
        for r in rows
    ]


def all_runs() -> list[dict]:
    with reporting_engine().connect() as connection:
        return [dict(row._mapping) for row in connection.execute(select(pipeline_runs).order_by("started_at"))]


@pytest.fixture
def week_of_activity():
    """W1 y W2 con actividad en los dos almacenes y dos clientes, más ruido que el pipeline debe ignorar."""
    insert(
        event(INBOUND, at(W1), quantity=500, order_id=1),
        event(OUTBOUND, at(W1), order_id=1),
        event(INBOUND, at(W2), quantity=300, order_id=2),
        event(INBOUND, at(W2), quantity=120, order_id=3),
        *(event(OUTBOUND, at(W2, 8 + n), order_id=10 + n) for n in range(4)),
        event(STOCKOUT, at(W2)),
        event(DISCREPANCY, at(W2)),
        event(OUTBOUND, at(W2), warehouse="zaragoza", client_id="electro-brand", order_id=1),
        event(OUTBOUND, at(W2), client_id="MAL", order_id=99),  # rechazado por calidad
        event(OUTBOUND, at(W2), environment="production", order_id=50),  # otro entorno
        event("login_failed", at(W2)),  # otro tipo de evento
    )


def test_full_run_writes_the_report_and_records_the_run(week_of_activity):
    run = run_weekly_performance(now=NOW, trigger="api", triggered_by="user-1")
    assert kpis(report_rows()) == [
        ("los_angeles", "fashion-co", W1, 500, 1, 0, 0, 0.0),
        ("los_angeles", "fashion-co", W2, 420, 4, 1, 1, 0.25),
        ("zaragoza", "electro-brand", W2, 0, 1, 0, 0, 0.0),
    ]
    assert run["status"] == "succeeded" and run["pipeline"] == PIPELINE_NAME
    assert (run["trigger"], run["triggered_by"], run["environment"]) == ("api", "user-1", "development")
    assert (run["week_from"], run["week_to"]) == (W1, W2)
    assert (run["events_read"], run["events_rejected"], run["rows_upserted"], run["rows_deleted"]) == (12, 1, 3, 0)
    stats = run["stats"]
    assert stats["weeks"] == [W1.isoformat(), W2.isoformat()]
    assert stats["events_read"] == {INBOUND: 3, OUTBOUND: 7, STOCKOUT: 1, DISCREPANCY: 1}
    assert stats["events_rejected"] == {OUTBOUND: {"invalid_client_id": 1}}
    assert stats["changes"] == {
        W1.isoformat(): {"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 0},
        W2.isoformat(): {"inserted": 2, "updated": 0, "unchanged": 0, "deleted": 0},
    }
    # Sin órdenes en el inventario de prueba: todos los eventos de órdenes «sobran» frente a la fuente de verdad.
    assert "capture_gap" in stats["warnings"] and "silent_days" in stats["warnings"]
    assert stats["source_health"]["total_events"] == 13  # también cuenta login_failed: la captura funciona
    assert run["phase"] == "loaded" and run["request_id"] is None
    assert run["finished_at"] is not None and run["duration_ms"] >= 0 and run["error"] is None
    assert {row["run_id"] for row in report_rows()} == {run["id"]}  # cada fila dice qué ejecución la escribió


def test_rerunning_is_idempotent(week_of_activity):
    run_weekly_performance(now=NOW)
    first = report_rows()
    run_weekly_performance(now=NOW)
    second = report_rows()
    assert kpis(first) == kpis(second)
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert len(all_runs()) == 2


def test_late_events_are_picked_up_by_the_next_run(week_of_activity):
    run_weekly_performance(now=NOW)
    insert(event(OUTBOUND, at(W2, 23), order_id=200))  # llega tarde, con fecha de W2
    next_monday = NOW + timedelta(days=7)
    run_weekly_performance(now=next_monday)  # ventana W2–W3: W2 se recalcula
    w2 = [r for r in report_rows() if r["week_start"] == W2 and r["client_id"] == "fashion-co"]
    assert w2[0]["outbound_orders_count"] == 5


def test_each_run_records_which_published_weeks_it_changed(week_of_activity):
    first = run_weekly_performance(now=NOW)
    insert(event(OUTBOUND, at(W2, 23), order_id=201))  # evento tardío de W2
    second = run_weekly_performance(now=NOW)
    assert second["stats"]["changes"] == {
        W1.isoformat(): {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0},
        W2.isoformat(): {"inserted": 0, "updated": 1, "unchanged": 1, "deleted": 0},
    }
    rows = {(r["week_start"], r["client_id"]): r for r in report_rows()}
    # La fila corregida y las demás de la ventana apuntan a la última ejecución; la anterior queda en el registro.
    assert rows[(W2, "fashion-co")]["run_id"] == second["id"] != first["id"]
    assert runs.get_run(first["id"])["status"] == "succeeded"


def test_a_failed_week_is_filled_by_the_next_scheduled_run(week_of_activity, monkeypatch):
    original = flow.load_rows

    def failing_load(*args, **kwargs):
        raise ReportingStorageError("OperationalError")

    monkeypatch.setattr(flow, "load_rows", failing_load)
    with pytest.raises(PipelineRunFailed):
        run_weekly_performance(week_start=W1, weeks=1, now=NOW)  # el lunes de W2 falla
    monkeypatch.setattr(flow, "load_rows", original)
    run_weekly_performance(now=NOW)  # el lunes siguiente: ventana W1–W2
    assert {r["week_start"] for r in report_rows()} == {W1, W2}


def test_failure_is_recorded_and_the_report_is_unchanged(week_of_activity, monkeypatch):
    run_weekly_performance(now=NOW)
    before = kpis(report_rows())
    insert(event(OUTBOUND, at(W2), order_id=300))

    def broken(*args, **kwargs):
        raise ValueError("detalle interno que no debe guardarse")

    monkeypatch.setattr(flow, "aggregate_rows", broken)
    with pytest.raises(PipelineRunFailed) as error:
        run_weekly_performance(now=NOW)
    assert error.value.run["status"] == "failed" and error.value.run["error"] == "ValueError"
    assert error.value.run["phase"] == "validated"  # checkpoint: murió en aggregate
    assert kpis(report_rows()) == before
    latest = runs.latest_run(PIPELINE_NAME)
    assert latest["status"] == "failed" and "detalle" not in latest["error"]
    assert latest["rows_upserted"] is None


def test_storage_errors_are_recorded_by_type_only(week_of_activity, monkeypatch):
    def broken(*args, **kwargs):
        raise ReportingStorageError("OperationalError (SQLSTATE 08006)")

    monkeypatch.setattr(flow, "extract_events", broken)
    with pytest.raises(PipelineRunFailed):
        run_weekly_performance(now=NOW)
    assert runs.latest_run(PIPELINE_NAME)["error"] == "OperationalError (SQLSTATE 08006)"


def test_registry_unavailable_raises_before_doing_anything(monkeypatch):
    def broken(**kwargs):
        raise ReportingStorageError("OperationalError")

    called = []
    monkeypatch.setattr(runs, "start_run", broken)
    monkeypatch.setattr(flow, "extract_events", lambda *a: called.append(a))
    with pytest.raises(ReportingStorageError):
        run_weekly_performance(now=NOW)
    assert called == []


def test_invalid_window_records_nothing():
    with pytest.raises(WindowError):
        run_weekly_performance(week_start=W2 + timedelta(days=1), now=NOW)
    assert all_runs() == []


def test_stale_running_run_is_marked_abandoned():
    stale_id = uuid.uuid4()
    with reporting_engine().begin() as connection:
        connection.execute(
            pipeline_runs.insert().values(
                id=stale_id,
                pipeline=PIPELINE_NAME,
                status="running",
                trigger="cli",
                environment="development",
                week_from=W1,
                week_to=W2,
                started_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
    run_weekly_performance(now=NOW)
    stale = runs.get_run(stale_id)
    assert (stale["status"], stale["error"]) == ("failed", "abandoned")


def test_load_failure_leaves_the_aggregated_checkpoint(week_of_activity, monkeypatch):
    def broken(*args, **kwargs):
        raise ReportingStorageError("OperationalError")

    monkeypatch.setattr(flow, "load_rows", broken)
    with pytest.raises(PipelineRunFailed) as error:
        run_weekly_performance(now=NOW)
    assert error.value.run["phase"] == "aggregated" and report_rows() == []


def test_a_running_run_of_another_process_blocks_a_second_one():
    other_id = uuid.uuid4()
    with reporting_engine().begin() as connection:
        connection.execute(
            pipeline_runs.insert().values(
                id=other_id,
                pipeline=PIPELINE_NAME,
                status="running",
                trigger="cli",
                environment="development",
                week_from=W1,
                week_to=W2,
                started_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
    with pytest.raises(PipelineAlreadyRunning):  # p. ej. el cron a las 06:00 y un POST a las 06:05
        run_weekly_performance(now=NOW)
    assert runs.get_run(other_id)["status"] == "running"
    assert [run["id"] for run in all_runs()] == [other_id]  # el segundo no llega a registrarse ni a leer nada


def test_only_one_run_at_a_time_in_the_process(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = flow.compute_weekly_performance

    def slow(*args, **kwargs):
        entered.set()
        release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(flow, "compute_weekly_performance", slow)
    worker = threading.Thread(target=lambda: run_weekly_performance(now=NOW))
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(PipelineAlreadyRunning):
            run_weekly_performance(now=NOW)
    finally:
        release.set()
        worker.join(5)
    assert [run["status"] for run in all_runs()] == ["succeeded"]


def test_pipeline_never_modifies_telemetry_events(week_of_activity):
    before = telemetry_count()
    run_weekly_performance(now=NOW)
    run_weekly_performance(now=NOW)
    assert telemetry_count() == before


def test_compute_has_no_side_effects(week_of_activity):
    computation = compute_weekly_performance(WeekWindow(first=W1, last=W2), "development")
    assert len(computation.rows) == 3 and computation.total_read == 12 and computation.total_rejected == 1
    assert report_rows() == [] and all_runs() == []


def test_environment_comes_from_telemetry_config(week_of_activity, monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENVIRONMENT", "production")
    run = run_weekly_performance(now=NOW)
    assert run["environment"] == "production"
    assert kpis(report_rows()) == [("los_angeles", "fashion-co", W2, 0, 1, 0, 0, 0.0)]


# --- Línea de comandos ----------------------------------------------------------------------------------------------


@pytest.fixture
def frozen_now(monkeypatch):
    """`python -m app.reporting` usa la hora real: se fija para que la ventana por defecto sea W1–W2."""
    original = flow.resolve_window
    monkeypatch.setattr(flow, "resolve_window", lambda week_start, weeks, now=None: original(week_start, weeks, NOW))
    monkeypatch.setattr(cli, "resolve_window", lambda week_start, weeks, now=None: original(week_start, weeks, NOW))


def test_cli_runs_the_pipeline(week_of_activity, frozen_now, capsys):
    assert cli.main([]) == 0
    assert "succeeded" in capsys.readouterr().out
    assert runs.latest_run(PIPELINE_NAME)["trigger"] == "cli"
    assert len(report_rows()) == 3


def test_cli_dry_run_prints_rows_and_writes_nothing(week_of_activity, frozen_now, capsys):
    assert cli.main(["--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["weeks"] == [W1.isoformat(), W2.isoformat()] and len(output["rows"]) == 3
    assert report_rows() == [] and all_runs() == []


def test_cli_rejects_an_unfinished_week(frozen_now, capsys):
    assert cli.main(["--week-start", "2026-11-09"]) == 2
    assert "aún no ha terminado" in capsys.readouterr().err


def test_cli_reports_a_failed_run(week_of_activity, frozen_now, monkeypatch, capsys):
    monkeypatch.setattr(flow, "aggregate_rows", lambda *a: 1 / 0)
    assert cli.main([]) == 1
    assert "ZeroDivisionError" in capsys.readouterr().err
