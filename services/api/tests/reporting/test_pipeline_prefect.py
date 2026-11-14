"""Resiliencia del flow de Prefect (`data/pipelines/pipeline.py`, PIPELINE_DESIGN.md §18).

Reintentos solo ante fallos transitorios, tareas opcionales frente a críticas (`return_state=True`), estados finales de
Prefect, caché de la transformación (`cache_key_fn` + `cache_expiration`), snapshot de evaluación y trazabilidad entre
Prefect y `reporting.pipeline_runs`.

Ejecutar desde services/api: uv run pytest tests/reporting/test_pipeline_prefect.py
"""

import json
from datetime import timedelta

import pytest
from prefect.client.orchestration import get_client
from sqlalchemy import select

from app.reporting import runs
from app.reporting.tables import ReportingStorageError, reporting_engine, weekly_performance
from app.reporting.weeks import WeekWindow
from data.pipelines import pipeline as flow
from data.pipelines.pipeline import (
    PIPELINE_NAME,
    TRANSFORM_CACHE_EXPIRATION,
    Extraction,
    PipelineRunFailed,
    retry_if_transient,
    run_weekly_performance,
    transform_cache_key,
)
from tests.reporting.helpers import DISCREPANCY, INBOUND, NOW, OUTBOUND, W1, W2, at, event, frame, insert

TRANSIENT = ReportingStorageError("OperationalError (SQLSTATE 08006)", transient=True)
PERMANENT = ReportingStorageError("ProgrammingError (SQLSTATE 42P01)", transient=False)


def report() -> list[tuple]:
    with reporting_engine().connect() as connection:
        rows = connection.execute(select(weekly_performance).order_by("week_start", "warehouse", "client_id")).all()
    return [
        (r.warehouse, r.client_id, r.week_start, r.inbound_units_count, r.outbound_orders_count, r.discrepancy_rate)
        for r in rows
    ]


@pytest.fixture
def activity():
    insert(
        event(INBOUND, at(W1), quantity=500, order_id=1),
        event(INBOUND, at(W2), quantity=300, order_id=2),
        *(event(OUTBOUND, at(W2, 8 + n), order_id=10 + n) for n in range(4)),
        event(DISCREPANCY, at(W2)),
    )


@pytest.fixture
def no_retry_wait(monkeypatch):
    """Mismos reintentos, sin esperar entre ellos (el número de reintentos es lo que se prueba)."""
    for name in ("extract_task", "load_task", "register_run", "close_run", "observe_task"):
        monkeypatch.setattr(flow, name, getattr(flow, name).with_options(retry_delay_seconds=0))


def failing(original, errors: list[Exception]):
    """Función que lanza cada error de `errors` en orden y después delega en `original`. `.calls` cuenta llamadas."""

    def wrapper(*args, **kwargs):
        wrapper.calls += 1
        if errors:
            raise errors.pop(0)
        return original(*args, **kwargs)

    wrapper.calls = 0
    return wrapper


# --- Reintentos ------------------------------------------------------------------------------------------------------


def test_retry_policy_matches_the_documented_values():
    assert (flow.extract_task.retries, flow.extract_task.retry_delay_seconds) == (3, [2, 10, 30])
    assert (flow.load_task.retries, flow.load_task.retry_delay_seconds) == (2, [5, 15])
    assert flow.extract_task.retry_condition_fn is retry_if_transient
    assert flow.load_task.retry_condition_fn is retry_if_transient


def test_a_transient_extract_failure_is_retried_and_the_run_succeeds(activity, no_retry_wait, monkeypatch):
    extract = failing(flow.extract_events, [TRANSIENT, TRANSIENT])
    monkeypatch.setattr(flow, "extract_events", extract)
    run = run_weekly_performance(now=NOW)
    assert extract.calls == 3  # 1 intento + 2 reintentos
    assert run["status"] == "succeeded" and run["rows_upserted"] == 2


def test_a_persistent_transient_failure_gives_up_after_three_retries(activity, no_retry_wait, monkeypatch):
    extract = failing(flow.extract_events, [TRANSIENT] * 10)
    monkeypatch.setattr(flow, "extract_events", extract)
    with pytest.raises(PipelineRunFailed) as error:
        run_weekly_performance(now=NOW)
    assert extract.calls == 4
    assert error.value.run["status"] == "failed" and error.value.run["phase"] == "started"
    assert error.value.run["error"] == "OperationalError (SQLSTATE 08006)"


def test_a_permanent_failure_is_not_retried(activity, no_retry_wait, monkeypatch):
    extract = failing(flow.extract_events, [PERMANENT])
    monkeypatch.setattr(flow, "extract_events", extract)
    with pytest.raises(PipelineRunFailed):
        run_weekly_performance(now=NOW)
    assert extract.calls == 1


def test_a_transient_load_failure_is_retried_without_duplicates(activity, no_retry_wait, monkeypatch):
    load = failing(flow.load_rows, [TRANSIENT])
    monkeypatch.setattr(flow, "load_rows", load)
    run = run_weekly_performance(now=NOW)
    assert load.calls == 2 and run["status"] == "succeeded"
    assert report() == [
        ("los_angeles", "fashion-co", W1, 500, 0, 0.0),
        ("los_angeles", "fashion-co", W2, 300, 4, 0.25),
    ]


def test_retry_condition_only_accepts_transient_storage_errors():
    class FakeState:
        def __init__(self, error):
            self.error = error

        def result(self):
            if self.error:
                raise self.error
            return None

    assert retry_if_transient(None, None, FakeState(TRANSIENT)) is True
    assert retry_if_transient(None, None, FakeState(PERMANENT)) is False
    assert retry_if_transient(None, None, FakeState(ValueError("bug"))) is False
    assert retry_if_transient(None, None, FakeState(None)) is False


# --- Tareas opcionales y críticas ------------------------------------------------------------------------------------


def test_optional_observe_failure_continues_and_marks_the_run_partial(activity, monkeypatch):
    monkeypatch.setattr(flow, "observe", lambda *a: 1 / 0)
    run = run_weekly_performance(now=NOW)
    assert run["status"] == "succeeded" and run["phase"] == "loaded"
    assert run["stats"]["outcome"] == "partial" and run["stats"]["degraded"] == ["observe"]
    assert run["stats"]["warnings"] == ["observability_unavailable"]
    assert len(report()) == 2  # el reporte se cargó igual


def test_optional_snapshot_failure_continues_and_marks_the_run_partial(activity, tmp_path, monkeypatch):
    not_a_directory = tmp_path / "fichero"
    not_a_directory.write_text("no es una carpeta")
    monkeypatch.setenv("PIPELINE_EVAL_DIR", str(not_a_directory))
    run = run_weekly_performance(now=NOW)
    assert run["status"] == "succeeded"
    assert run["stats"]["outcome"] == "partial" and run["stats"]["degraded"] == ["eval_snapshot"]
    assert "eval_snapshot" not in run["stats"] and len(report()) == 2


def test_successful_run_writes_the_evaluation_snapshot(activity, eval_dir):
    run = run_weekly_performance(now=NOW)
    assert run["stats"]["outcome"] == "succeeded" and run["stats"]["degraded"] == []
    (snapshot,) = eval_dir.glob("*.json")
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    assert document["run_id"] == str(run["id"]) and document["pipeline"] == PIPELINE_NAME
    assert document["weeks"] == [W1.isoformat(), W2.isoformat()]
    assert [(r["week_start"], r["inbound_units_count"]) for r in document["rows"]] == [
        (W1.isoformat(), 500),
        (W2.isoformat(), 300),
    ]
    assert document["changes"] == run["stats"]["changes"]


def test_critical_load_failure_fails_the_run_even_with_optional_tasks_ok(activity, monkeypatch, eval_dir):
    monkeypatch.setattr(flow, "load_rows", failing(flow.load_rows, [PERMANENT]))
    with pytest.raises(PipelineRunFailed) as error:
        run_weekly_performance(now=NOW)
    run = error.value.run
    assert (run["status"], run["phase"], run["error"]) == ("failed", "aggregated", "ProgrammingError (SQLSTATE 42P01)")
    assert report() == [] and list(eval_dir.glob("*.json")) == []  # sin carga no hay snapshot ni éxito


def test_prefect_final_states_distinguish_success_partial_and_failure(activity, monkeypatch):
    window = {"week_from": W1, "week_to": W2}
    ok = flow.weekly_performance_flow(**window, return_state=True)
    assert ok.is_completed()

    monkeypatch.setattr(flow, "observe", lambda *a: 1 / 0)
    partial = flow.weekly_performance_flow(**window, return_state=True)
    assert partial.is_completed() and partial.result()["stats"]["outcome"] == "partial"

    monkeypatch.setattr(flow, "load_rows", failing(flow.load_rows, [PERMANENT]))
    failed = flow.weekly_performance_flow(**window, return_state=True)
    assert failed.is_failed()
    assert runs.latest_run(PIPELINE_NAME)["status"] == "failed"


def test_the_run_id_is_the_prefect_flow_run_id(activity):
    run = run_weekly_performance(now=NOW)
    with get_client(sync_client=True) as client:
        flow_run = client.read_flow_run(run["id"])
    assert flow_run.name == run["stats"]["prefect"]["flow_run_name"]
    assert flow_run.state.is_completed()
    assert flow_run.parameters["week_from"] == W1.isoformat() and flow_run.parameters["week_to"] == W2.isoformat()


# --- Caché de la transformación --------------------------------------------------------------------------------------


@pytest.fixture
def counted_transform(monkeypatch):
    original = flow.transform_events
    calls = []

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(flow, "transform_events", counting)
    return calls


def test_rerunning_on_the_same_data_reuses_the_cached_transformation(activity, counted_transform):
    first = run_weekly_performance(now=NOW)
    first_rows = report()
    second = run_weekly_performance(now=NOW)
    assert first["stats"]["prefect"]["transform_cache"] == "miss"
    assert second["stats"]["prefect"]["transform_cache"] == "hit"
    assert len(counted_transform) == 1  # la segunda ejecución no recalculó
    assert report() == first_rows  # y el resultado es idéntico (idempotencia)
    assert second["stats"]["changes"][W2.isoformat()]["unchanged"] == 1


def test_new_source_data_invalidates_the_cache(activity, counted_transform):
    run_weekly_performance(now=NOW)
    insert(event(OUTBOUND, at(W2, 22), order_id=99))  # evento tardío
    second = run_weekly_performance(now=NOW)
    assert second["stats"]["prefect"]["transform_cache"] == "miss" and len(counted_transform) == 2
    assert report()[1][4] == 5  # el KPI refleja el evento nuevo: nunca un resultado obsoleto


def test_another_window_is_another_cache_entry(activity, counted_transform):
    run_weekly_performance(now=NOW)
    other = run_weekly_performance(week_start=W2, weeks=1, now=NOW)
    assert other["stats"]["prefect"]["transform_cache"] == "miss" and len(counted_transform) == 2


def test_a_code_change_invalidates_the_cache(activity, counted_transform, monkeypatch):
    run_weekly_performance(now=NOW)
    monkeypatch.setattr(flow, "CODE_VERSION", "otra-version-del-codigo")
    assert run_weekly_performance(now=NOW)["stats"]["prefect"]["transform_cache"] == "miss"


def test_cache_key_covers_every_input_that_determines_the_result(monkeypatch):
    events = frame(event(INBOUND, at(W2), quantity=5, order_id=1))
    extraction = Extraction(events=events, environment="development", fingerprint="a" * 64)
    weeks = WeekWindow(first=W1, last=W2).weeks
    key = transform_cache_key(None, {"extraction": extraction, "weeks": weeks})
    assert key.startswith("weekly-kpis-")
    assert key == transform_cache_key(None, {"extraction": extraction, "weeks": weeks})
    variants = [
        {"extraction": Extraction(events, "development", "b" * 64), "weeks": weeks},
        {"extraction": Extraction(events, "production", "a" * 64), "weeks": weeks},
        {"extraction": extraction, "weeks": weeks[1:]},
    ]
    assert all(transform_cache_key(None, params) != key for params in variants)
    monkeypatch.setattr(flow, "CODE_VERSION", "otra")
    assert transform_cache_key(None, {"extraction": extraction, "weeks": weeks}) != key


def test_cache_expiration_is_one_day():
    assert TRANSFORM_CACHE_EXPIRATION == timedelta(days=1)
    assert flow.transform_task.cache_expiration == TRANSFORM_CACHE_EXPIRATION
    assert flow.transform_task.cache_key_fn is transform_cache_key
