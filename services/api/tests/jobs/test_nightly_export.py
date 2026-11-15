"""Proceso nocturno (`scripts/nightly_export.py`): fecha objetivo, exportación CSV, subprocess del pipeline,
orquestación con `job_runs`, fallos, logs e independencia de la API. Base SQLite temporal por test (`conftest.py`).

El pipeline real se sustituye por una función falsa o por pequeños scripts de Python lanzados con el mismo
`run_pipeline`; el recorrido completo con el pipeline del Hito 6 y PostgreSQL está en docs/telemetry/nightly-export.md.
"""

import csv
import importlib.util
import io
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.jobs import job_runner as jr
from app.telemetry.storage import telemetry_engine, telemetry_events

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "nightly_export.py"

spec = importlib.util.spec_from_file_location("nightly_export", SCRIPT)
nightly = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nightly  # `dataclass` busca el módulo ahí al resolver las anotaciones
spec.loader.exec_module(nightly)

DAY = date(2026, 11, 14)
LOG_LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z (INFO|WARNING|ERROR) job=nightly_export "
    r"target_date=(\S+) run_id=(\S+) status=(\S+) event=(\S+) "
)


# --- Utilidades ---------------------------------------------------------------------------------------------------


def make_log() -> tuple[nightly.JobLog, io.StringIO]:
    stream = io.StringIO()
    return nightly.configure_logging(stream), stream


def events_of(stream: io.StringIO) -> list[tuple[str, str, str]]:
    """(nivel, estado, evento) de cada línea de log principal."""
    found = []
    for line in stream.getvalue().splitlines():
        match = LOG_LINE.match(line)
        if match:
            found.append((match.group(1), match.group(4), match.group(5)))
    return found


def names(stream: io.StringIO) -> list[str]:
    return [event for _, _, event in events_of(stream)]


def insert_events(*timestamps: datetime, environment: str = "development") -> list[uuid.UUID]:
    ids = []
    rows = []
    for moment in timestamps:
        event_id = uuid.uuid4()
        ids.append(event_id)
        rows.append(
            {
                "id": event_id,
                "event_type": "inbound_order_created",
                "timestamp": moment,
                "service": "backend",
                "tags": {"warehouse": "zaragoza", "client_id": "cliente-ñ", "quantity": 3},
                "session_id": None,
                "user_id": "usr_abc",
                "request_id": uuid.uuid4(),
                "schema_version": "1.0.0",
                "environment": environment,
            }
        )
    with telemetry_engine().begin() as connection:
        connection.execute(telemetry_events.insert(), rows)
    return ids


class FakePipeline:
    """Sustituye a `run_pipeline`: cuenta las llamadas y opcionalmente falla."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[date] = []
        self.error = error

    def __call__(self, target_date: date) -> nightly.PipelineResult:
        self.calls.append(target_date)
        if self.error is not None:
            raise self.error
        return nightly.PipelineResult(returncode=0, duration_seconds=0.1, summary="Ejecución x succeeded", stderr_tail=[])


def run(tmp_path, pipeline=None, target=DAY):
    log, stream = make_log()
    pipeline = pipeline or FakePipeline()
    code = nightly.run_nightly_export(target, log, export_dir=tmp_path / "raw", pipeline=pipeline)
    return code, stream, pipeline


# --- 5.1 Fecha objetivo ---------------------------------------------------------------------------------------------


def test_default_target_date_is_yesterday_in_utc():
    assert nightly.resolve_target_date(None, datetime(2026, 11, 15, 0, 30, tzinfo=UTC)) == date(2026, 11, 14)
    assert nightly.resolve_target_date("", datetime(2026, 11, 15, 23, 59, tzinfo=UTC)) == date(2026, 11, 14)


def test_the_local_time_zone_does_not_change_the_target_date():
    # 01:30 del 15 en UTC+2 son las 23:30 del 14 en UTC: «ayer» en UTC es el 13.
    plus_two = timezone(timedelta(hours=2))
    assert nightly.resolve_target_date(None, datetime(2026, 11, 15, 1, 30, tzinfo=plus_two)) == date(2026, 11, 13)
    # 20:00 del 14 en Los Ángeles (UTC-8) son las 04:00 del 15 en UTC: «ayer» en UTC es el 14.
    los_angeles = timezone(timedelta(hours=-8))
    assert nightly.resolve_target_date(None, datetime(2026, 11, 14, 20, 0, tzinfo=los_angeles)) == date(2026, 11, 14)


def test_target_date_overrides_the_default():
    now = datetime(2026, 11, 15, 2, 0, tzinfo=UTC)
    assert nightly.resolve_target_date("2026-11-01", now) == date(2026, 11, 1)
    assert nightly.resolve_target_date("  2026-11-14 ", now) == date(2026, 11, 14)


@pytest.mark.parametrize(
    "value", ["2026/11/14", "14-11-2026", "20261114", "2026-11-14T00:00", "2026-02-30", "2026-13-01", "ayer", "2026-1-5"]
)
def test_invalid_target_dates_are_rejected_with_a_clear_error(value):
    with pytest.raises(nightly.TargetDateError) as error:
        nightly.resolve_target_date(value, datetime(2026, 11, 15, tzinfo=UTC))
    assert "TARGET_DATE" in str(error.value)


@pytest.mark.parametrize("value", ["2026-11-15", "2026-11-16", "2030-01-01"])
def test_days_that_have_not_ended_in_utc_are_rejected(value):
    with pytest.raises(nightly.TargetDateError, match="aún no ha terminado"):
        nightly.resolve_target_date(value, datetime(2026, 11, 15, 23, 59, tzinfo=UTC))


@pytest.mark.parametrize(
    ("target", "week_start"),
    [
        (date(2026, 11, 9), date(2026, 11, 2)),  # lunes: su semana aún no ha terminado
        (date(2026, 11, 14), date(2026, 11, 2)),  # sábado
        (date(2026, 11, 15), date(2026, 11, 9)),  # domingo: su semana termina ese día
        (date(2026, 11, 16), date(2026, 11, 9)),
    ],
)
def test_pipeline_week_start_is_the_last_complete_iso_week(target, week_start):
    assert nightly.pipeline_week_start(target) == week_start
    assert week_start.weekday() == 0


def test_main_rejects_an_invalid_target_date_without_touching_the_database(monkeypatch, capsys):
    monkeypatch.setenv("TARGET_DATE", "2026-02-30")
    assert nightly.main([]) == nightly.EXIT_USAGE
    assert "invalid_target_date" in capsys.readouterr().err
    assert jr.list_job_runs(nightly.JOB_NAME) == []


# --- 5.2 Exportación CSV ------------------------------------------------------------------------------------------


def read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_export_writes_only_the_events_of_the_target_day_in_utc(tmp_path):
    start = datetime(2026, 11, 14, tzinfo=UTC)
    insert_events(start - timedelta(microseconds=1), start + timedelta(days=1))  # 23:59:59.999999 del 13 · 00:00 del 15
    inside = insert_events(start + timedelta(hours=23, minutes=59, seconds=59), start, environment="production")
    out = tmp_path / "raw"
    result = nightly.export_telemetry_csv(DAY, out)
    assert result.created and result.rows == 2
    assert result.path == out / "telemetry_2026-11-14.csv"
    rows = read_csv(result.path)
    assert rows[0] == list(nightly.CSV_COLUMNS)
    assert [row[0] for row in rows[1:]] == [str(inside[1]), str(inside[0])]  # ordenadas por timestamp
    first = dict(zip(rows[0], rows[1]))
    assert first["timestamp"] == "2026-11-14T00:00:00+00:00"
    assert first["tags"] == '{"client_id":"cliente-ñ","quantity":3,"warehouse":"zaragoza"}'
    assert first["session_id"] == "" and first["environment"] == "production"
    assert list(out.iterdir()) == [result.path]  # sin temporales


def test_export_columns_are_the_real_columns_of_telemetry_events():
    assert nightly.CSV_COLUMNS == (
        "id", "event_type", "timestamp", "service", "tags", "session_id", "user_id", "request_id",
        "schema_version", "environment",
    )


def test_a_day_without_events_produces_a_header_only_csv(tmp_path):
    result = nightly.export_telemetry_csv(DAY, tmp_path / "nueva" / "carpeta")
    assert result.created and result.rows == 0
    assert read_csv(result.path) == [list(nightly.CSV_COLUMNS)]


def test_an_existing_csv_is_never_overwritten(tmp_path):
    path = tmp_path / "telemetry_2026-11-14.csv"
    path.write_text("contenido previo\n", encoding="utf-8")
    insert_events(datetime(2026, 11, 14, 12, tzinfo=UTC))
    result = nightly.export_telemetry_csv(DAY, tmp_path)
    assert not result.created and result.rows is None
    assert path.read_text(encoding="utf-8") == "contenido previo\n"


def test_a_csv_that_appears_during_the_export_is_respected(tmp_path, monkeypatch):
    def link_that_finds_a_file(source, destination):
        Path(destination).write_text("otro proceso\n", encoding="utf-8")
        raise FileExistsError(destination)

    monkeypatch.setattr(nightly.os, "link", link_that_finds_a_file)
    out = tmp_path / "raw"
    result = nightly.export_telemetry_csv(DAY, out)
    assert not result.created
    assert result.path.read_text(encoding="utf-8") == "otro proceso\n"
    assert list(out.iterdir()) == [result.path]


def test_a_failed_export_leaves_no_partial_file(tmp_path, monkeypatch):
    insert_events(*(datetime(2026, 11, 14, 10, tzinfo=UTC) + timedelta(seconds=i) for i in range(5)))
    original = nightly._csv_value
    calls = {"n": 0}

    def explode_midway(value):
        calls["n"] += 1
        if calls["n"] > 25:  # a mitad de la tercera fila
            raise OSError(28, "No space left on device")
        return original(value)

    monkeypatch.setattr(nightly, "_csv_value", explode_midway)
    out = tmp_path / "raw"
    with pytest.raises(nightly.ExportError, match="No space left"):
        nightly.export_telemetry_csv(DAY, out)
    assert list(out.iterdir()) == []


# --- 5.3 Subprocess -----------------------------------------------------------------------------------------------


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_pipeline_command_uses_the_same_interpreter_and_no_shell():
    command = nightly.pipeline_command(DAY)
    assert command == [sys.executable, str(nightly.PIPELINE_SCRIPT), "--week-start", "2026-11-02"]
    assert nightly.PIPELINE_SCRIPT.is_file()


def test_run_pipeline_captures_the_output_and_the_summary():
    result = nightly.run_pipeline(
        DAY,
        command=python(
            "import sys; print('Prefect…', file=sys.stderr); print('Ejecución abc succeeded: 1 → 2'); "
            "print('Avisos: capture_gap.')"
        ),
    )
    assert result.returncode == 0
    assert result.summary == "Ejecución abc succeeded: 1 → 2"  # UTF-8 también en Windows
    assert result.stdout_lines == ("Avisos: capture_gap.",)
    assert result.stderr_tail == ["Prefect…"]


def test_a_non_zero_exit_code_is_a_pipeline_error_with_its_stderr():
    code = (
        "import sys; print('traza', file=sys.stderr); print('La ejecución ha fallado: X', file=sys.stderr); "
        "print('INFO | prefect - Stopping temporary server', file=sys.stderr); sys.exit(1)"
    )
    with pytest.raises(nightly.PipelineError) as error:
        nightly.run_pipeline(DAY, command=python(code))
    assert error.value.returncode == 1
    # La causa es el mensaje del pipeline, no la última línea (que es de Prefect).
    assert str(error.value) == "el pipeline terminó con código 1: La ejecución ha fallado: X"
    assert error.value.stderr_tail == ["traza", "La ejecución ha fallado: X", "INFO | prefect - Stopping temporary server"]


def test_a_pipeline_that_cannot_start_is_a_pipeline_error():
    with pytest.raises(nightly.PipelineError, match="no se pudo lanzar"):
        nightly.run_pipeline(DAY, command=[str(Path("no-existe") / "python-inexistente")])


def test_a_slow_pipeline_is_killed_at_the_timeout():
    started = time.monotonic()
    with pytest.raises(nightly.PipelineTimeout) as error:
        nightly.run_pipeline(DAY, timeout=1, command=python("import sys, time; print('arrancando', file=sys.stderr, flush=True); time.sleep(60)"))
    assert time.monotonic() - started < 15
    assert "timeout de 1 s" in str(error.value)
    assert error.value.stderr_tail == ["arrancando"]


GRANDCHILD = """
import subprocess, sys, time
# Como el servidor temporal de Prefect: un nieto que hereda stdout/stderr y sobrevive al hijo.
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(40)"])
open(sys.argv[1], "w").write(str(child.pid))
time.sleep(60)
"""


def test_the_timeout_works_even_if_a_grandchild_keeps_the_outputs_open(tmp_path):
    """Regresión: con `capture_output=True` (pipes), en Windows `subprocess.run` esperaría al nieto tras el timeout."""
    pid_file = tmp_path / "grandchild.pid"
    started = time.monotonic()
    try:
        with pytest.raises(nightly.PipelineTimeout):
            nightly.run_pipeline(DAY, timeout=3, command=[sys.executable, "-c", GRANDCHILD, str(pid_file)])
        assert time.monotonic() - started < 20
    finally:
        if pid_file.exists():
            _kill(int(pid_file.read_text()))


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
    else:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def test_redact_hides_passwords_in_urls():
    line = "fallo en postgresql+psycopg://postgres.ref:mi-clave@pooler:5432/postgres"
    assert nightly.redact(line) == "fallo en postgresql+psycopg://postgres.ref:***@pooler:5432/postgres"


# --- 5.4 Orquestación ---------------------------------------------------------------------------------------------


def test_a_successful_run_goes_pending_processing_completed(tmp_path):
    insert_events(datetime(2026, 11, 14, 8, tzinfo=UTC))
    code, stream, pipeline = run(tmp_path)
    assert code == nightly.EXIT_OK
    assert pipeline.calls == [DAY]
    [record] = jr.list_job_runs(nightly.JOB_NAME, DAY)
    assert record["status"] == jr.COMPLETED
    assert record["started_at"] is not None and record["finished_at"] >= record["started_at"]
    assert record["error_message"] is None
    assert len(read_csv(tmp_path / "raw" / "telemetry_2026-11-14.csv")) == 2
    assert names(stream) == [
        "job_started", "lock_acquired", "processing", "export_started", "export_completed",
        "pipeline_started", "pipeline_completed", "job_completed",
    ]
    statuses = [status for _, status, _ in events_of(stream)]
    assert statuses == ["-", "pending", "processing", "processing", "processing", "processing", "processing", "completed"]


def test_every_log_line_identifies_the_run(tmp_path):
    code, stream, _ = run(tmp_path)
    run_id = str(jr.list_job_runs(nightly.JOB_NAME)[0]["id"])
    lines = stream.getvalue().splitlines()
    assert lines and all(LOG_LINE.match(line) for line in lines)
    assert all("target_date=2026-11-14" in line for line in lines)
    assert all(f"run_id={run_id}" in line for line in lines[1:])  # desde que existe el registro


def test_running_twice_the_same_date_exports_and_processes_once(tmp_path):
    pipeline = FakePipeline()
    run(tmp_path, pipeline)
    csv_file = tmp_path / "raw" / "telemetry_2026-11-14.csv"
    first_mtime = csv_file.stat().st_mtime_ns
    code, stream, _ = run(tmp_path, pipeline)
    assert code == nightly.EXIT_OK
    assert pipeline.calls == [DAY]  # una sola ejecución del pipeline
    assert csv_file.stat().st_mtime_ns == first_mtime
    assert [r["status"] for r in jr.list_job_runs(nightly.JOB_NAME)] == [jr.COMPLETED]
    assert names(stream) == ["job_started", "skipped_duplicate"]
    assert events_of(stream)[-1][1] == "skipped"


def test_an_active_run_blocks_a_second_one_without_running_the_pipeline(tmp_path):
    active = jr.create_job_run(nightly.JOB_NAME, DAY - timedelta(days=1))
    jr.update_job_status(active["id"], jr.PROCESSING)
    code, stream, pipeline = run(tmp_path)
    assert code == nightly.EXIT_LOCKED
    assert pipeline.calls == []
    assert not (tmp_path / "raw").exists()
    assert len(jr.list_job_runs(nightly.JOB_NAME)) == 1  # el bloqueado no crea filas
    assert names(stream) == ["job_started", "skipped_locked"]
    assert str(active["id"]) in stream.getvalue()


def test_a_completed_date_detected_inside_the_acquisition_is_a_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(jr, "has_completed_for_date", lambda *_: False)  # simula la carrera tras la comprobación previa
    first = jr.acquire_job_run(nightly.JOB_NAME, DAY)
    jr.update_job_status(first["id"], jr.PROCESSING)
    jr.update_job_status(first["id"], jr.COMPLETED)
    code, stream, pipeline = run(tmp_path)
    assert code == nightly.EXIT_OK and pipeline.calls == []
    assert names(stream) == ["job_started", "skipped_duplicate"]


# --- 5.5 Fallos -----------------------------------------------------------------------------------------------------


def only_run() -> dict:
    [record] = jr.list_job_runs(nightly.JOB_NAME)
    return record


def test_an_export_error_marks_the_run_failed_and_skips_the_pipeline(tmp_path, monkeypatch):
    def broken_engine():
        raise RuntimeError("disco no disponible")

    monkeypatch.setattr(nightly, "telemetry_engine", broken_engine)
    with pytest.raises(nightly.ExportError):
        run(tmp_path)
    record = only_run()
    assert record["status"] == jr.FAILED and "disco no disponible" in record["error_message"]
    assert record["started_at"] is not None and record["finished_at"] is not None


def test_a_pipeline_error_marks_the_run_failed_and_propagates(tmp_path):
    error = nightly.PipelineError("el pipeline terminó con código 1: La ejecución ha fallado", returncode=1, stderr_tail=["a", "b"])
    log, stream = make_log()
    with pytest.raises(nightly.PipelineError):
        nightly.run_nightly_export(DAY, log, export_dir=tmp_path, pipeline=FakePipeline(error))
    record = only_run()
    assert record["status"] == jr.FAILED
    assert record["error_message"] == "PipelineError: el pipeline terminó con código 1: La ejecución ha fallado"
    found = events_of(stream)
    assert ("ERROR", "processing", "pipeline_failed") in found
    assert [e for _, _, e in found].count("pipeline_stderr") == 2
    assert found[-1] == ("ERROR", "failed", "job_failed")
    assert not jr.has_processing_lock(nightly.JOB_NAME)  # el candado queda libre


def test_a_pipeline_timeout_marks_the_run_failed(tmp_path):
    with pytest.raises(nightly.PipelineTimeout):
        run(tmp_path, FakePipeline(nightly.PipelineTimeout("el pipeline superó el timeout de 1800 s y se ha detenido")))
    assert "timeout" in only_run()["error_message"]


def test_a_failed_date_is_retried_and_reuses_the_existing_csv(tmp_path):
    with pytest.raises(nightly.PipelineError):
        run(tmp_path, FakePipeline(nightly.PipelineError("código 1")))
    code, stream, pipeline = run(tmp_path)
    assert code == nightly.EXIT_OK and pipeline.calls == [DAY]
    assert [r["status"] for r in jr.list_job_runs(nightly.JOB_NAME, DAY)] == [jr.FAILED, jr.COMPLETED]
    assert "ya existía: no se sobrescribe" in stream.getvalue()


def test_a_failure_to_mark_failed_does_not_hide_the_original_error(tmp_path, monkeypatch):
    real_update = jr.update_job_status

    def update(run_id, status, **kwargs):
        if status == jr.FAILED:
            raise jr.JobRunsStorageError("OperationalError (SQLSTATE 08006)")
        return real_update(run_id, status, **kwargs)

    monkeypatch.setattr(jr, "update_job_status", update)
    log, stream = make_log()
    with pytest.raises(nightly.PipelineError, match="código 1"):
        nightly.run_nightly_export(DAY, log, export_dir=tmp_path, pipeline=FakePipeline(nightly.PipelineError("código 1")))
    assert ("ERROR", "processing", "status_update_failed") in events_of(stream)
    record = only_run()
    assert record["status"] == jr.PROCESSING  # se queda activa: la recupera una ejecución posterior
    later = datetime.now(UTC) + jr.STALE_AFTER + timedelta(minutes=1)
    jr.recover_abandoned_runs(nightly.JOB_NAME, now=later)
    assert only_run()["status"] == jr.FAILED


def test_a_failure_when_marking_completed_ends_in_failed(tmp_path, monkeypatch):
    real_update = jr.update_job_status

    def update(run_id, status, **kwargs):
        if status == jr.COMPLETED:
            raise jr.JobRunsStorageError("OperationalError (SQLSTATE 57P01)")
        return real_update(run_id, status, **kwargs)

    monkeypatch.setattr(jr, "update_job_status", update)
    log, stream = make_log()
    with pytest.raises(jr.JobRunsStorageError):
        nightly.run_nightly_export(DAY, log, export_dir=tmp_path, pipeline=FakePipeline())
    assert only_run()["status"] == jr.FAILED
    assert "status_update_failed" in names(stream)


def test_an_interruption_marks_the_run_failed(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, FakePipeline(KeyboardInterrupt()))
    assert only_run()["error_message"] == "KeyboardInterrupt"


def test_an_unexpected_error_is_logged_with_its_traceback(tmp_path):
    with pytest.raises(ZeroDivisionError):
        run(tmp_path, FakePipeline(ZeroDivisionError("division by zero")))
    assert only_run()["status"] == jr.FAILED


def test_a_database_connection_error_fails_without_secrets_in_the_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://jobuser:s3cr3t-pass@127.0.0.1:1/jobs")
    monkeypatch.delenv("TARGET_DATE", raising=False)
    monkeypatch.setattr(nightly, "EXPORT_DIR", tmp_path / "raw")
    assert nightly.main([]) == nightly.EXIT_FAILED
    err = capsys.readouterr().err
    assert "event=connection_error" in err and "s3cr3t" not in err
    assert not (tmp_path / "raw").exists()


def test_main_returns_the_lock_exit_code(monkeypatch, tmp_path):
    jr.create_job_run(nightly.JOB_NAME, DAY)
    monkeypatch.setenv("TARGET_DATE", "2026-11-13")
    assert nightly.main([]) == nightly.EXIT_LOCKED


# --- Independencia de la API --------------------------------------------------------------------------------------


def test_fastapi_does_not_import_the_job_runner_or_the_nightly_script():
    code = (
        "import sys, app.main; "
        "print(sorted(m for m in sys.modules if m.startswith('app.jobs') or 'nightly' in m))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "services" / "api", capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
    source = (ROOT / "services" / "api" / "app" / "main.py").read_text(encoding="utf-8")
    assert "jobs" not in source and "nightly" not in source
