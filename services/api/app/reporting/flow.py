"""Flow del Reporte Semanal de Desempeño por Almacén y Cliente (PIPELINE_DESIGN.md §5).

`run_weekly_performance` resuelve la ventana, registra la ejecución y encadena los subflows:

    extract (telemetry_events, solo lectura) → validate → aggregate → load (reporting, una transacción)

`compute_weekly_performance` es la parte sin escrituras (extract → validate → aggregate): la usa el flow y el modo
`--dry-run` de la línea de comandos.

Concurrencia: una sola ejecución a la vez por proceso (`PipelineAlreadyRunning` → 409). Entre procesos distintos (API
y `cron`) el resultado sigue siendo correcto porque la carga es idempotente.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import pandas as pd

from app.reporting import runs
from app.reporting.aggregate import aggregate_rows
from app.reporting.extract import extract_events
from app.reporting.load import load_rows
from app.reporting.tables import ReportingStorageError
from app.reporting.validate import validate_events
from app.reporting.weeks import DEFAULT_WEEKS, WeekWindow, resolve_window
from app.telemetry.config import get_environment

logger = logging.getLogger("trackflow.reporting")

PIPELINE_NAME = "weekly_warehouse_client_performance"
Trigger = Literal["api", "cli"]


class PipelineAlreadyRunning(RuntimeError):
    """Ya hay una ejecución de este pipeline en curso en este proceso."""


class PipelineRunFailed(RuntimeError):
    """La ejecución ha fallado y ha quedado registrada como `failed`. `run` es su registro (si se pudo leer)."""

    def __init__(self, run: dict[str, Any] | None, error: str) -> None:
        super().__init__(error)
        self.run = run
        self.error = error


@dataclass
class Computation:
    """Resultado de los subflows sin escrituras."""

    window: WeekWindow
    environment: str
    rows: list[dict]
    events_read: dict[str, int]
    rejected: dict[str, dict[str, int]]

    @property
    def total_read(self) -> int:
        return sum(self.events_read.values())

    @property
    def total_rejected(self) -> int:
        return sum(sum(by_reason.values()) for by_reason in self.rejected.values())

    def stats(self) -> dict[str, Any]:
        return {
            "weeks": [week.isoformat() for week in self.window.weeks],
            "events_read": self.events_read,
            "events_rejected": self.rejected,
        }


def compute_weekly_performance(window: WeekWindow, environment: str) -> Computation:
    """extract → validate → aggregate. Solo lee `telemetry_events`; no escribe nada."""
    raw: pd.DataFrame = extract_events(window, environment)
    validated = validate_events(raw)
    if validated.rejected:
        logger.warning("Pipeline semanal · validate: eventos rechazados %s", validated.rejected)
    rows = aggregate_rows(validated.valid, window)
    return Computation(
        window=window,
        environment=environment,
        rows=rows,
        events_read=validated.events_read,
        rejected=validated.rejected,
    )


_run_lock = threading.Lock()


def _error_kind(error: Exception) -> str:
    """Tipo de error para el registro: nunca el mensaje (podría llevar datos o la cadena de conexión)."""
    if isinstance(error, ReportingStorageError):
        return str(error)
    return type(error).__name__


def run_weekly_performance(
    *,
    week_start: date | None = None,
    weeks: int = DEFAULT_WEEKS,
    trigger: Trigger = "cli",
    triggered_by: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ejecuta el pipeline completo y devuelve el registro de la ejecución (`succeeded`).

    - `WindowError` (sin registrar nada) si los parámetros no son válidos.
    - `PipelineAlreadyRunning` si ya hay una ejecución en curso en este proceso.
    - `ReportingStorageError` si ni siquiera se puede registrar la ejecución (base caída, migración sin aplicar).
    - `PipelineRunFailed` si falla un subflow: la ejecución queda `failed` y la tabla de destino, sin cambios.
    """
    window = resolve_window(week_start, weeks, now)
    if not _run_lock.acquire(blocking=False):
        raise PipelineAlreadyRunning("Ya hay una ejecución del pipeline semanal en curso.")
    try:
        environment = get_environment()
        started_at = datetime.now(UTC)
        began = time.perf_counter()
        run_id = runs.start_run(
            pipeline=PIPELINE_NAME,
            trigger=trigger,
            triggered_by=triggered_by,
            environment=environment,
            week_from=window.first,
            week_to=window.last,
            started_at=started_at,
        )
        logger.info(
            "Pipeline semanal · inicio %s (%s, %s): semanas %s → %s",
            run_id,
            trigger,
            environment,
            window.first.isoformat(),
            window.last.isoformat(),
        )

        def elapsed_ms() -> int:
            return round((time.perf_counter() - began) * 1000)

        try:
            computation = compute_weekly_performance(window, environment)
            loaded = load_rows(computation.rows, window, computed_at=datetime.now(UTC))
        except Exception as error:  # cualquier fallo de un subflow cierra la ejecución como `failed`
            kind = _error_kind(error)
            logger.error("Pipeline semanal · %s falló: %s", run_id, kind)
            try:
                runs.finish_run(
                    run_id, status="failed", finished_at=datetime.now(UTC), duration_ms=elapsed_ms(), error=kind
                )
                run = runs.get_run(run_id)
            except ReportingStorageError:
                run = None
            raise PipelineRunFailed(run, kind) from error

        runs.finish_run(
            run_id,
            status="succeeded",
            finished_at=datetime.now(UTC),
            duration_ms=elapsed_ms(),
            events_read=computation.total_read,
            events_rejected=computation.total_rejected,
            rows_upserted=loaded.rows_upserted,
            rows_deleted=loaded.rows_deleted,
            stats=computation.stats(),
        )
        logger.info(
            "Pipeline semanal · fin %s: %d eventos leídos, %d rechazados, %d filas escritas, %d eliminadas",
            run_id,
            computation.total_read,
            computation.total_rejected,
            loaded.rows_upserted,
            loaded.rows_deleted,
        )
        return runs.get_run(run_id) or {}
    finally:
        _run_lock.release()
