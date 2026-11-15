"""Proceso nocturno de telemetría (DEV-53): exporta un día de `telemetry_events` a CSV y lanza el pipeline del Hito 6.

Es un proceso **independiente de la API**: no se importa desde FastAPI ni se arranca en su ciclo de vida. Lo dispara
un programador externo (cron, 02:00 UTC) o una persona. Documentación: docs/telemetry/nightly-export.md.

    uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py
    $env:TARGET_DATE = "2026-11-14"; uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py

(o `python scripts/nightly_export.py` con el entorno virtual de `services/api` activado y las variables cargadas).

Recorrido de una ejecución (job `nightly_export`, registrada en `job_runs`):

1. Fecha objetivo: el día anterior en UTC, o `TARGET_DATE=YYYY-MM-DD` (solo días ya terminados en UTC).
2. Idempotencia: si ya hay una ejecución `completed` para esa fecha, termina sin hacer nada (código 0).
3. Candado: crea el registro `pending` (adquisición atómica en la base). Si otra ejecución está activa, termina
   sin crear nada (código 75).
4. `processing` → exporta `data/raw/telemetry_YYYY-MM-DD.csv` si aún no existe (copia de auditoría; el pipeline no
   lo lee) → lanza `data/pipelines/pipeline.py` en un subprocess (lee PostgreSQL, registra `pipeline_runs`).
5. `completed`; ante cualquier excepción, `failed` con el error, y el proceso termina con código distinto de cero.

Códigos de salida: 0 completada u omitida por estar ya completada · 1 fallida · 2 `TARGET_DATE` no válida ·
75 omitida porque otra ejecución tiene el candado (`EX_TEMPFAIL`: volver a intentarlo más tarde) · 130 Ctrl+C ·
143 `SIGTERM`.
"""

import argparse
import csv
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path
from typing import Any

# `python scripts/nightly_export.py` solo añade `scripts/` a sys.path: se añade la API (paquete `app`, conexión a la
# base y job runner). Al final, para no tapar nada.
REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.append(str(API_ROOT))

from sqlalchemy import make_url, select  # noqa: E402

from app.database import get_database_url  # noqa: E402
from app.jobs import job_runner  # noqa: E402
from app.jobs.job_runner import (  # noqa: E402
    COMPLETED,
    FAILED,
    PENDING,
    PROCESSING,
    InvalidTransition,
    JobAlreadyCompleted,
    JobAlreadyRunning,
    JobRunsStorageError,
    error_summary,
)
from app.telemetry.storage import telemetry_engine, telemetry_events  # noqa: E402

JOB_NAME = "nightly_export"
EXPORT_DIR = REPO_ROOT / "data" / "raw"
PIPELINE_SCRIPT = REPO_ROOT / "data" / "pipelines" / "pipeline.py"

# Una ejecución normal del pipeline tarda menos de un minuto (arranque del servidor temporal de Prefect incluido).
# 30 min es un margen amplio para un volumen muy superior y coincide con `ABANDON_AFTER` de `pipeline_runs`: si hay
# que matar al pipeline, su registro `running` lo recupera la siguiente ejecución. Es menor que `STALE_AFTER` de
# `job_runs` (2 h), así una ejecución viva nunca se toma por abandonada.
PIPELINE_TIMEOUT_SECONDS = 30 * 60
OUTPUT_TAIL_LINES = 15
EXPORT_BATCH_SIZE = 1000

CSV_COLUMNS = tuple(column.name for column in telemetry_events.columns)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_LOCKED = 75  # EX_TEMPFAIL (sysexits.h)
EXIT_INTERRUPTED = 130
EXIT_TERMINATED = 143


# --- Logging ------------------------------------------------------------------------------------------------------

LOG_FORMAT = (
    "%(asctime)s %(levelname)s job=%(job)s target_date=%(target_date)s run_id=%(run_id)s status=%(status)s "
    "event=%(event)s %(message)s"
)
_SECRET_IN_URL = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@\s]+@", re.IGNORECASE)


def redact(text: str) -> str:
    """Oculta la contraseña de cualquier URL con credenciales (`esquema://usuario:***@host`)."""
    return _SECRET_IN_URL.sub(r"\1***@", text)


class UTCFormatter(logging.Formatter):
    """Marca de tiempo ISO 8601 en UTC con milisegundos (`2026-11-15T02:00:00.123Z`), independiente de la zona local."""

    converter = time.gmtime

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return time.strftime("%Y-%m-%dT%H:%M:%S", self.converter(record.created)) + f".{int(record.msecs):03d}Z"


class JobLog:
    """Logger con el contexto de la ejecución: cada línea lleva job, fecha objetivo, id de ejecución, estado y evento.

    `status` es el estado de `job_runs` de esta ejecución (`-` si aún no hay registro; `skipped` cuando se omite,
    que no es un estado de la tabla: una ejecución omitida no crea fila).
    """

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.context: dict[str, str] = {"job": JOB_NAME, "target_date": "-", "run_id": "-", "status": "-"}

    def bind(self, **values: Any) -> None:
        self.context.update({key: str(value) for key, value in values.items()})

    def _log(self, level: int, event: str, message: str, *, exc_info: bool = False) -> None:
        self.logger.log(level, redact(message), extra={**self.context, "event": event}, exc_info=exc_info)

    def info(self, event: str, message: str) -> None:
        self._log(logging.INFO, event, message)

    def warning(self, event: str, message: str) -> None:
        self._log(logging.WARNING, event, message)

    def error(self, event: str, message: str, *, exc_info: bool = False) -> None:
        self._log(logging.ERROR, event, message, exc_info=exc_info)


def configure_logging(stream=None) -> JobLog:
    """Logger `nightly_export` a stderr (cron o Docker lo redirigen al fichero de log), sin propagar a la raíz."""
    logger = logging.getLogger(JOB_NAME)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(UTCFormatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return JobLog(logger)


# --- Fecha objetivo -----------------------------------------------------------------------------------------------

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class TargetDateError(ValueError):
    """`TARGET_DATE` no es una fecha `YYYY-MM-DD` válida o es un día que aún no ha terminado en UTC."""


def resolve_target_date(value: str | None, now: datetime | None = None) -> date:
    """Día a procesar: `TARGET_DATE` si está definida (y no vacía) o, por defecto, el día anterior **en UTC**.

    Solo se aceptan días ya terminados en UTC: exportar un día a medias y marcarlo `completed` haría que nunca se
    volviera a exportar completo (la idempotencia lo daría por hecho).
    """
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    if value is None or not value.strip():
        return today - timedelta(days=1)
    raw = value.strip()
    shown = raw if len(raw) <= 40 else raw[:40] + "…"
    if not _ISO_DATE.fullmatch(raw):
        raise TargetDateError(f"TARGET_DATE={shown!r} no tiene el formato YYYY-MM-DD.")
    try:
        target = date.fromisoformat(raw)
    except ValueError:
        raise TargetDateError(f"TARGET_DATE={shown!r} no es una fecha válida.") from None
    if target >= today:
        raise TargetDateError(
            f"TARGET_DATE={raw} aún no ha terminado en UTC (hoy es {today.isoformat()}): solo se procesan días completos."
        )
    return target


# --- Exportación CSV ----------------------------------------------------------------------------------------------


class ExportError(Exception):
    """La exportación del CSV ha fallado (base, disco o permisos). No queda ningún fichero a medias."""


@dataclass(frozen=True)
class ExportResult:
    path: Path
    created: bool  # False: el fichero ya existía y no se ha tocado
    rows: int | None  # filas exportadas (None si no se ha exportado)


def csv_path(target_date: date, directory: Path = EXPORT_DIR) -> Path:
    return directory / f"telemetry_{target_date.isoformat()}.csv"


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)  # SQLite: sin zona, siempre UTC
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def export_telemetry_csv(target_date: date, directory: Path = EXPORT_DIR) -> ExportResult:
    """Exporta los eventos de `target_date` (`[00:00, 24:00)` UTC) a `telemetry_YYYY-MM-DD.csv` si aún no existe.

    - Nunca sobrescribe: si el fichero existe, no se toca (`created=False`).
    - Escritura atómica: se escribe un temporal en la misma carpeta, se fuerza a disco y se publica con `os.link`,
      que falla si el destino ya existe (a diferencia de `os.replace`, que lo sustituiría). Si algo falla, el
      temporal se borra y no queda un CSV incompleto con el nombre definitivo.
    - Sin cargarlo todo en memoria: la consulta se lee por lotes (`yield_per`, cursor de servidor en PostgreSQL),
      en una transacción `READ ONLY`.
    - Cero eventos: CSV con solo la cabecera (deja constancia de que ese día no hubo eventos).

    Columnas: las de `telemetry_events`, en su orden. Fechas en ISO 8601 UTC, `tags` como JSON, UTF-8.
    """
    path = csv_path(target_date, directory)
    if path.exists():
        return ExportResult(path, created=False, rows=None)
    start = datetime.combine(target_date, day_time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    timestamp = telemetry_events.c.timestamp
    statement = (
        select(*(telemetry_events.c[name] for name in CSV_COLUMNS))
        .where(timestamp >= start, timestamp < end)
        .order_by(timestamp, telemetry_events.c.id)
    )
    tmp: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
        tmp = Path(tmp_name)
        rows = 0
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_COLUMNS)
            with telemetry_engine().connect() as connection:
                connection = connection.execution_options(postgresql_readonly=True, yield_per=EXPORT_BATCH_SIZE)
                with connection.begin():
                    for row in connection.execute(statement):
                        writer.writerow([_csv_value(value) for value in row])
                        rows += 1
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return ExportResult(path, created=False, rows=None)  # apareció mientras tanto: se respeta
        return ExportResult(path, created=True, rows=rows)
    except Exception as error:
        raise ExportError(error_summary(error)) from error
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


# --- Pipeline en un subprocess --------------------------------------------------------------------------------------


class PipelineError(Exception):
    """El pipeline terminó con un código distinto de cero (o no pudo lanzarse)."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr_tail: list[str] | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail or []


class PipelineTimeout(PipelineError):
    """El pipeline superó `PIPELINE_TIMEOUT_SECONDS` y se ha matado."""


@dataclass(frozen=True)
class PipelineResult:
    returncode: int
    duration_seconds: float
    summary: str  # línea «Ejecución <id> <estado>: …» del pipeline (o la última de stdout)
    stderr_tail: list[str]
    stdout_lines: tuple[str, ...] = ()  # resto de stdout (avisos, etapas opcionales con fallo)


def pipeline_week_start(target_date: date) -> date:
    """Lunes de la última semana ISO **completa** al final de `target_date` (el `--week-start` del pipeline).

    El pipeline del Hito 6 es semanal y solo calcula semanas completas: con la fecha por defecto (ayer) coincide con
    su ventana por defecto; con `TARGET_DATE` (recuperar un día antiguo) recalcula las semanas de esa fecha.
    """
    monday = target_date - timedelta(days=target_date.weekday())
    return monday if target_date.weekday() == 6 else monday - timedelta(weeks=1)


def pipeline_command(target_date: date) -> list[str]:
    """Mismo intérprete que este proceso (`sys.executable`: el entorno virtual de la API, con Prefect)."""
    return [sys.executable, str(PIPELINE_SCRIPT), "--week-start", pipeline_week_start(target_date).isoformat()]


# Mensajes con los que la línea de comandos del pipeline explica su código de salida (1 fallida, 2 parámetros o en
# curso). Prefect escribe después otras líneas («Stopping temporary server…»), que no son la causa.
_PIPELINE_FAILURE_PREFIXES = ("La ejecución ha fallado", "Error:")


def _failure_reason(err_lines: list[str]) -> str:
    for line in reversed(err_lines):
        if line.startswith(_PIPELINE_FAILURE_PREFIXES):
            return line
    return err_lines[-1] if err_lines else "sin salida de error"


def _read_output(handle) -> list[str]:
    handle.seek(0)
    return [redact(line) for line in handle.read().decode("utf-8", errors="replace").splitlines() if line.strip()]


def run_pipeline(
    target_date: date, *, timeout: float = PIPELINE_TIMEOUT_SECONDS, command: list[str] | None = None
) -> PipelineResult:
    """Lanza el pipeline como proceso hijo con `subprocess.run` (sin `shell=True`) y comprueba su código de salida.

    stdout y stderr se capturan en **ficheros temporales**, no en pipes: el pipeline arranca el servidor temporal de
    Prefect como otro proceso que hereda sus salidas; si hubiera que matar al pipeline por timeout, ese nieto
    mantendría abiertos los pipes y `subprocess.run` se quedaría esperando (en Windows) a que se cerraran.
    """
    command = command or pipeline_command(target_date)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # el pipeline imprime «→»: sin esto, cp1252 en Windows
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise PipelineTimeout(
                f"el pipeline superó el timeout de {timeout:g} s y se ha detenido",
                stderr_tail=_read_output(stderr)[-OUTPUT_TAIL_LINES:],
            ) from None
        except OSError as error:
            raise PipelineError(f"no se pudo lanzar el pipeline: {error_summary(error)}") from error
        out_lines, err_lines = _read_output(stdout), _read_output(stderr)
    duration = time.monotonic() - started
    if completed.returncode != 0:
        raise PipelineError(
            f"el pipeline terminó con código {completed.returncode}: {_failure_reason(err_lines)}",
            returncode=completed.returncode,
            stderr_tail=err_lines[-OUTPUT_TAIL_LINES:],
        )
    summary = next((line for line in out_lines if line.startswith("Ejecución ")), out_lines[-1] if out_lines else "")
    return PipelineResult(
        returncode=0,
        duration_seconds=duration,
        summary=summary,
        stderr_tail=err_lines[-OUTPUT_TAIL_LINES:],
        stdout_lines=tuple(line for line in out_lines[-OUTPUT_TAIL_LINES:] if line != summary),
    )


# --- Orquestación ---------------------------------------------------------------------------------------------------


class TerminatedBySignal(BaseException):
    """`SIGTERM` recibido (p. ej. `docker stop` o `kill`): se trata como una interrupción, igual que Ctrl+C."""


def _on_sigterm(signum, frame) -> None:
    raise TerminatedBySignal("SIGTERM recibido")


def _database_label() -> str:
    try:
        return make_url(get_database_url()).get_backend_name()
    except Exception:
        return "desconocida"


def _mark_failed(run_id: uuid.UUID, error: BaseException, log: JobLog) -> None:
    """Pasa la ejecución a `failed`. Nunca lanza: un fallo aquí no debe tapar la excepción original."""
    try:
        job_runner.update_job_status(run_id, FAILED, error_message=error_summary(error))
    except Exception as secondary:
        log.error(
            "status_update_failed",
            f"no se pudo marcar la ejecución como failed ({error_summary(secondary)}); seguirá activa hasta que la "
            f"recupere una ejecución posterior (más de {job_runner.STALE_AFTER} activa).",
        )
        return
    log.bind(status=FAILED)
    log.error("job_failed", f"ejecución fallida: {error_summary(error)}")


def _log_failure(error: BaseException, log: JobLog) -> None:
    """Un evento ERROR por tipo de fallo, para saber en qué etapa murió la ejecución."""
    if isinstance(error, PipelineError):
        event = "pipeline_timeout" if isinstance(error, PipelineTimeout) else "pipeline_failed"
        log.error(event, str(error))
        for line in error.stderr_tail:
            log.error("pipeline_stderr", line)
    elif isinstance(error, ExportError):
        log.error("export_failed", f"la exportación ha fallado: {error}")
    elif isinstance(error, (JobRunsStorageError, InvalidTransition)):
        log.error("status_update_failed", f"no se pudo actualizar el estado: {error_summary(error)}")
    elif isinstance(error, (KeyboardInterrupt, TerminatedBySignal)):
        log.error("interrupted", f"ejecución interrumpida: {error_summary(error)}")
    else:
        log.error("unexpected_error", f"excepción inesperada: {error_summary(error)}", exc_info=True)


def run_nightly_export(
    target_date: date, log: JobLog, *, export_dir: Path | None = None, pipeline=run_pipeline
) -> int:
    """Ejecuta el job para `target_date` y devuelve el código de salida. Propaga las excepciones de una ejecución
    adquirida **después** de dejarla en `failed`."""
    export_dir = export_dir or EXPORT_DIR
    log.bind(target_date=target_date.isoformat())
    started = time.monotonic()
    log.info("job_started", f"inicio del proceso nocturno (base: {_database_label()}, pid {os.getpid()})")

    # 1-2. Idempotencia y candado. Sin candado no se crea ninguna fila ni se toca nada.
    try:
        if job_runner.has_completed_for_date(JOB_NAME, target_date):
            log.bind(status="skipped")
            log.info("skipped_duplicate", "ya hay una ejecución completed para esta fecha: no se repite el trabajo")
            return EXIT_OK
        run = job_runner.acquire_job_run(JOB_NAME, target_date)
    except JobAlreadyCompleted:
        log.bind(status="skipped")
        log.info("skipped_duplicate", "otra ejecución completó esta fecha mientras se adquiría el candado")
        return EXIT_OK
    except JobAlreadyRunning as busy:
        active = busy.active or {}
        log.bind(status="skipped")
        log.info(
            "skipped_locked",
            f"otra ejecución tiene el candado (run_id={active.get('id', '?')}, status={active.get('status', '?')}, "
            f"target_date={active.get('target_date', '?')}): se aborta sin ejecutar el pipeline",
        )
        return EXIT_LOCKED
    except JobRunsStorageError as error:
        log.error("connection_error", f"no se pudo consultar ni registrar la ejecución en job_runs: {error}")
        raise
    except Exception as error:
        log.error("unexpected_error", f"excepción inesperada antes de adquirir: {error_summary(error)}", exc_info=True)
        raise

    run_id = run["id"]
    log.bind(run_id=run_id, status=PENDING)
    log.info("lock_acquired", "registro pending creado: candado adquirido")
    try:
        job_runner.update_job_status(run_id, PROCESSING)
        log.bind(status=PROCESSING)
        log.info("processing", "ejecución en curso")

        path = csv_path(target_date, export_dir)
        shown = path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else str(path)
        log.info("export_started", f"exportando los eventos del día a {shown}")
        export = export_telemetry_csv(target_date, export_dir)
        if export.created:
            log.info("export_completed", f"CSV creado: {export.path.name} ({export.rows} eventos)")
        else:
            log.info("export_completed", f"el CSV {export.path.name} ya existía: no se sobrescribe")

        log.info(
            "pipeline_started",
            f"lanzando el pipeline (subprocess, --week-start {pipeline_week_start(target_date).isoformat()}, "
            f"timeout {PIPELINE_TIMEOUT_SECONDS} s)",
        )
        result = pipeline(target_date)
        log.info("pipeline_completed", f"pipeline correcto en {result.duration_seconds:.1f} s: {result.summary}")
        for line in result.stdout_lines:
            log.info("pipeline_stdout", line)

        job_runner.update_job_status(run_id, COMPLETED)
        log.bind(status=COMPLETED)
    except BaseException as error:
        _log_failure(error, log)
        _mark_failed(run_id, error, log)
        raise
    log.info("job_completed", f"ejecución completada en {time.monotonic() - started:.1f} s")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="python scripts/nightly_export.py",
        description=(
            "Proceso nocturno de telemetría: exporta un día de telemetry_events a data/raw/ y lanza el pipeline del "
            "Hito 6, con registro en job_runs. Fecha: el día anterior en UTC o TARGET_DATE=YYYY-MM-DD."
        ),
    ).parse_args(argv)
    if hasattr(sys.stderr, "reconfigure"):
        # Log en UTF-8 también cuando stderr va a un fichero en Windows (si no, cp1252 y acentos ilegibles).
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    log = configure_logging()
    try:
        target_date = resolve_target_date(os.environ.get("TARGET_DATE"))
    except TargetDateError as error:
        log.error("invalid_target_date", str(error))
        return EXIT_USAGE
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return run_nightly_export(target_date, log)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except TerminatedBySignal:
        return EXIT_TERMINATED
    except Exception:
        return EXIT_FAILED  # ya registrada (y la ejecución, en failed si se llegó a adquirir)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
