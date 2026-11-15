"""Job runner (`app/jobs/job_runner.py`) sobre SQLite: creación, máquina de estados, candado, idempotencia,
reintentos y recuperación de ejecuciones abandonadas. Cada test usa su propia base SQLite (`conftest.py`).

La exclusión mutua entre procesos de verdad se prueba contra PostgreSQL en `test_job_runner_postgres.py`.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.jobs import job_runner as jr
from app.jobs.job_runner import (
    COMPLETED,
    FAILED,
    PENDING,
    PROCESSING,
    InvalidTransition,
    JobAlreadyCompleted,
    JobAlreadyRunning,
    JobRunsStorageError,
)

JOB = "nightly_export"
DAY = date(2026, 11, 14)
NOW = datetime(2026, 11, 15, 2, 0, tzinfo=UTC)


def test_create_job_run_registers_a_pending_run():
    run = jr.create_job_run(JOB, DAY, now=NOW)
    assert run["status"] == PENDING
    assert run["job_name"] == JOB and run["target_date"] == DAY
    assert run["created_at"] == NOW
    assert run["started_at"] is None and run["finished_at"] is None and run["error_message"] is None
    assert jr.get_job_run(run["id"]) == run


def test_get_job_run_of_an_unknown_id_is_none():
    assert jr.get_job_run(uuid.uuid4()) is None


@pytest.mark.parametrize("name", ["", "Nightly", "nightly export", "1job", "job-name", "x" * 64])
def test_invalid_job_names_are_rejected(name):
    with pytest.raises(ValueError):
        jr.create_job_run(name, DAY)


def test_happy_path_transitions_record_their_timestamps():
    run = jr.create_job_run(JOB, DAY, now=NOW)
    started = NOW + timedelta(seconds=1)
    processing = jr.update_job_status(run["id"], PROCESSING, now=started)
    assert processing["status"] == PROCESSING and processing["started_at"] == started
    finished = NOW + timedelta(minutes=2)
    completed = jr.update_job_status(run["id"], COMPLETED, now=finished)
    assert completed["status"] == COMPLETED
    assert completed["started_at"] == started and completed["finished_at"] == finished
    assert completed["error_message"] is None


def test_processing_to_failed_keeps_the_start_and_stores_the_error():
    run = jr.create_job_run(JOB, DAY, now=NOW)
    jr.update_job_status(run["id"], PROCESSING, now=NOW)
    failed = jr.update_job_status(run["id"], FAILED, error_message="PipelineError: código 1", now=NOW)
    assert failed["status"] == FAILED and failed["started_at"] == NOW and failed["finished_at"] == NOW
    assert failed["error_message"] == "PipelineError: código 1"


def test_pending_to_failed_is_allowed_for_runs_that_never_started():
    run = jr.create_job_run(JOB, DAY, now=NOW)
    failed = jr.update_job_status(run["id"], FAILED, error_message="boom", now=NOW)
    assert failed["status"] == FAILED and failed["started_at"] is None


def test_failed_requires_an_error_message_and_long_messages_are_truncated():
    run = jr.create_job_run(JOB, DAY)
    with pytest.raises(ValueError):
        jr.update_job_status(run["id"], FAILED)
    failed = jr.update_job_status(run["id"], FAILED, error_message="x" * 5000)
    assert len(failed["error_message"]) == jr.MAX_ERROR_LENGTH


@pytest.mark.parametrize(
    ("path", "invalid"),
    [
        ([], COMPLETED),  # pending → completed (sin pasar por processing)
        ([PROCESSING, COMPLETED], PROCESSING),  # completed es final
        ([PROCESSING, COMPLETED], FAILED),
        ([FAILED], PROCESSING),  # failed es final: un reintento es otra fila
        ([PROCESSING], PROCESSING),
        ([], PENDING),  # pending no es destino de ninguna transición
    ],
)
def test_invalid_transitions_are_rejected_and_change_nothing(path, invalid):
    run = jr.create_job_run(JOB, DAY)
    for status in path:
        jr.update_job_status(run["id"], status, error_message="e" if status == FAILED else None)
    before = jr.get_job_run(run["id"])
    with pytest.raises(InvalidTransition):
        jr.update_job_status(run["id"], invalid, error_message="e" if invalid == FAILED else None)
    assert jr.get_job_run(run["id"]) == before


def test_unknown_status_and_unknown_run_are_rejected():
    run = jr.create_job_run(JOB, DAY)
    with pytest.raises(ValueError):
        jr.update_job_status(run["id"], "cancelled")
    with pytest.raises(InvalidTransition) as error:
        jr.update_job_status(uuid.uuid4(), PROCESSING)
    assert error.value.current is None


def test_a_transition_is_compare_and_set_so_only_one_of_two_racing_updates_wins():
    run = jr.create_job_run(JOB, DAY)
    jr.update_job_status(run["id"], PROCESSING)
    jr.update_job_status(run["id"], COMPLETED)
    with pytest.raises(InvalidTransition) as error:
        jr.update_job_status(run["id"], FAILED, error_message="tarde")
    assert error.value.current == COMPLETED
    assert jr.get_job_run(run["id"])["status"] == COMPLETED


def test_the_database_rejects_invalid_states_even_without_the_runner():
    jr.create_job_run(JOB, DAY)  # crea la tabla en SQLite con los mismos CHECK que la migración
    with pytest.raises(Exception) as error:
        with jr.job_runs_engine().begin() as connection:
            connection.execute(
                text(
                    "insert into job_runs (id, job_name, target_date, status, started_at, created_at) "
                    "values (:id, 'otro', '2026-11-14', 'cancelled', '2026-11-15', '2026-11-15')"
                ),
                {"id": uuid.uuid4().hex},
            )
    assert "CHECK constraint failed" in str(error.value)


# --- Candado ------------------------------------------------------------------------------------------------------


def test_a_second_active_run_of_the_same_job_is_rejected_without_creating_a_row():
    first = jr.create_job_run(JOB, DAY)
    with pytest.raises(JobAlreadyRunning) as error:
        jr.create_job_run(JOB, DAY - timedelta(days=1))  # también para otra fecha: una ejecución activa por job
    assert error.value.active["id"] == first["id"]
    assert len(jr.list_job_runs(JOB)) == 1


def test_the_processing_state_keeps_the_lock():
    run = jr.create_job_run(JOB, DAY)
    jr.update_job_status(run["id"], PROCESSING)
    assert jr.has_processing_lock(JOB)
    assert jr.get_active_job_run(JOB)["id"] == run["id"]
    with pytest.raises(JobAlreadyRunning):
        jr.acquire_job_run(JOB, DAY + timedelta(days=1))


def test_other_jobs_have_their_own_lock():
    jr.create_job_run(JOB, DAY)
    other = jr.create_job_run("weekly_backup", DAY)
    assert other["status"] == PENDING


@pytest.mark.parametrize("final", [COMPLETED, FAILED])
def test_reaching_a_final_state_releases_the_lock(final):
    run = jr.create_job_run(JOB, DAY)
    jr.update_job_status(run["id"], PROCESSING)
    jr.update_job_status(run["id"], final, error_message="e" if final == FAILED else None)
    assert not jr.has_processing_lock(JOB)
    assert jr.get_active_job_run(JOB) is None
    assert jr.create_job_run(JOB, DAY + timedelta(days=1))["status"] == PENDING


# --- Idempotencia y reintentos -------------------------------------------------------------------------------------


def _complete(target: date) -> dict:
    run = jr.create_job_run(JOB, target)
    jr.update_job_status(run["id"], PROCESSING)
    return jr.update_job_status(run["id"], COMPLETED)


def test_has_completed_for_date_only_counts_completed_runs_of_that_job_and_day():
    assert not jr.has_completed_for_date(JOB, DAY)
    run = jr.create_job_run(JOB, DAY)
    jr.update_job_status(run["id"], PROCESSING)
    assert not jr.has_completed_for_date(JOB, DAY)  # en curso
    jr.update_job_status(run["id"], FAILED, error_message="e")
    assert not jr.has_completed_for_date(JOB, DAY)  # fallida: se puede reintentar
    _complete(DAY)
    assert jr.has_completed_for_date(JOB, DAY)
    assert not jr.has_completed_for_date(JOB, DAY - timedelta(days=1))
    assert not jr.has_completed_for_date("weekly_backup", DAY)


def test_acquire_refuses_a_completed_date_and_leaves_no_row():
    _complete(DAY)
    with pytest.raises(JobAlreadyCompleted):
        jr.acquire_job_run(JOB, DAY)
    assert [run["status"] for run in jr.list_job_runs(JOB, DAY)] == [COMPLETED]
    assert jr.get_active_job_run(JOB) is None  # el INSERT del candado se deshizo


def test_a_failed_date_can_be_retried_and_keeps_its_history():
    first = jr.acquire_job_run(JOB, DAY, now=NOW)
    jr.update_job_status(first["id"], PROCESSING, now=NOW)
    jr.update_job_status(first["id"], FAILED, error_message="PipelineError", now=NOW)
    retry = jr.acquire_job_run(JOB, DAY, now=NOW + timedelta(minutes=5))
    jr.update_job_status(retry["id"], PROCESSING, now=NOW + timedelta(minutes=5))
    jr.update_job_status(retry["id"], COMPLETED, now=NOW + timedelta(minutes=6))
    assert [run["status"] for run in jr.list_job_runs(JOB, DAY)] == [FAILED, COMPLETED]
    assert jr.has_completed_for_date(JOB, DAY)


def test_multiple_dates_are_independent():
    _complete(DAY)
    run = jr.acquire_job_run(JOB, DAY + timedelta(days=1))
    assert run["status"] == PENDING


# --- Ejecuciones abandonadas (caída abrupta del proceso) -------------------------------------------------------------


def test_stale_processing_runs_are_marked_failed_before_acquiring():
    orphan = jr.create_job_run(JOB, DAY, now=NOW)
    jr.update_job_status(orphan["id"], PROCESSING, now=NOW)  # y el proceso muere aquí (SIGKILL)
    with pytest.raises(JobAlreadyRunning):
        jr.acquire_job_run(JOB, DAY, now=NOW + jr.STALE_AFTER - timedelta(minutes=1))
    later = NOW + jr.STALE_AFTER + timedelta(minutes=1)
    run = jr.acquire_job_run(JOB, DAY, now=later)
    recovered = jr.get_job_run(orphan["id"])
    assert recovered["status"] == FAILED and recovered["error_message"] == jr.ABANDONED
    assert recovered["started_at"] == NOW and recovered["finished_at"] == later
    assert run["status"] == PENDING


def test_stale_pending_runs_count_from_their_creation():
    orphan = jr.create_job_run(JOB, DAY, now=NOW)
    recovered = jr.recover_abandoned_runs(JOB, now=NOW + jr.STALE_AFTER + timedelta(seconds=1))
    assert [run["id"] for run in recovered] == [orphan["id"]]
    assert jr.get_job_run(orphan["id"])["started_at"] is None


def test_recovery_ignores_recent_runs_and_other_jobs():
    jr.create_job_run(JOB, DAY, now=NOW)
    old_other = jr.create_job_run("weekly_backup", DAY, now=NOW - timedelta(days=1))
    assert jr.recover_abandoned_runs(JOB, now=NOW + timedelta(minutes=30)) == []
    assert jr.get_job_run(old_other["id"])["status"] == PENDING


# --- Errores de base de datos ----------------------------------------------------------------------------------------


def test_database_errors_surface_as_storage_errors_without_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://jobuser:s3cr3t-pass@127.0.0.1:1/jobs")
    with pytest.raises(JobRunsStorageError) as error:
        jr.has_completed_for_date(JOB, DAY)
    assert "s3cr3t" not in str(error.value) and "jobuser" not in str(error.value)
    assert str(error.value) in ("OperationalError", "ConnectionTimeout")  # solo el tipo del error del driver


def test_error_summary_is_one_line_and_bounded():
    assert jr.error_summary(ValueError("a\nb   c")) == "ValueError: a b c"
    assert jr.error_summary(KeyboardInterrupt()) == "KeyboardInterrupt"
    assert len(jr.error_summary(RuntimeError("x" * 5000))) == jr.MAX_ERROR_LENGTH
