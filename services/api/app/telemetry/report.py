"""Reporte técnico de telemetría (`GET /telemetry/report`): periodo, caché y respuesta. Las métricas, en `analysis`.

Periodo `[from, to)` en UTC (inicio inclusivo, fin exclusivo):

| Parámetros | Periodo |
| --- | --- |
| ninguno | `to` = el minuto siguiente al actual (UTC, truncado); `from` = `to` − 7 días |
| solo `start_date` | `from` = `start_date`; `to` = el minuto siguiente al actual |
| solo `end_date` | `to` = `end_date`; `from` = `to` − 7 días |
| los dos | tal cual |

Las fechas sin zona horaria se interpretan como UTC. `from` debe ser anterior a `to` y el periodo no puede pasar de
366 días (`PeriodError` → 422). Redondear «ahora» al minuto siguiente hace que las peticiones sin fechas del mismo
minuto compartan clave de caché y que entren todos los eventos hasta el momento de la petición.

Caché (`app/cache.py`, la misma de los otros endpoints):

- `TTLCache` de **60 s** con clave `(origen de los datos, from, to)` en UTC: los periodos distintos nunca comparten
  resultado y dos formas de escribir el mismo instante (`+01:00` y `Z`) sí.
- **Un candado por clave**: si llegan a la vez varias peticiones del mismo periodo, solo una calcula y las demás
  esperan y reciben el resultado de la caché. Periodos distintos se calculan en paralelo.
- Si una métrica falla no se guarda nada (ni respuestas a medias): la siguiente petición vuelve a intentarlo.
- **Local al proceso**: con varios workers de uvicorn cada uno tiene su caché (la API se despliega con uno).
"""

import datetime as dt
import logging
import threading
import time
import weakref
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from app.cache import TTLCache, register
from app.database import get_database_url
from app.telemetry import analysis
from app.telemetry.analysis import to_utc

logger = logging.getLogger("trackflow.telemetry.report")

DEFAULT_PERIOD = timedelta(days=7)
MAX_PERIOD = timedelta(days=366)
REPORT_TTL_SECONDS = 60


class PeriodError(ValueError):
    """Periodo no válido. `field` es el parámetro al que se atribuye el error."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


# --- Respuesta ----------------------------------------------------------------------------------------------------


class ReportPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(alias="from", description="Inicio del periodo (UTC, inclusivo).")
    to: datetime = Field(description="Fin del periodo (UTC, exclusivo).")


class DailyEvents(BaseModel):
    date: dt.date = Field(description="Día UTC.")
    total_events: int = Field(description="Eventos de cualquier tipo registrados ese día.")


class ErrorsByType(BaseModel):
    error_category: str = Field(description="Categoría de la incidencia (authentication, validation, frontend…).")
    event_type: str = Field(description="Evento del catálogo que la registra.")
    reason: str | None = Field(description="Motivo, del campo de `tags` que define el catálogo (o nulo).")
    errors: int = Field(description="Incidencias en el periodo.")
    share_pct: float | None = Field(description="Porcentaje sobre el total de incidencias del periodo.")


class DailyErrors(BaseModel):
    date: dt.date = Field(description="Día UTC.")
    errors: int = Field(description="Incidencias técnicas registradas ese día.")


class DailyAuthFailureRate(BaseModel):
    date: dt.date = Field(description="Día UTC.")
    failed: int = Field(description="`login_failed` del día.")
    succeeded: int = Field(description="`login_succeeded` del día.")
    attempts: int = Field(description="Intentos: fallidos + correctos.")
    failure_rate_pct: float | None = Field(description="failed / attempts × 100 (nulo sin intentos).")


class FormSubmissionFailures(BaseModel):
    form_id: str | None = Field(description="Formulario del backoffice.")
    submissions: int = Field(description="Envíos (`form_submitted`) en el periodo.")
    failed: int = Field(description="Envíos con un `outcome` distinto de `success`.")
    failure_rate_pct: float | None = Field(description="failed / submissions × 100.")


class ReportMetrics(BaseModel):
    events_per_day: list[DailyEvents]
    error_rate_by_type: list[ErrorsByType]
    errors_per_day: list[DailyErrors]
    auth_failure_rate: list[DailyAuthFailureRate]
    submission_failures_by_form: list[FormSubmissionFailures]


class TelemetryReport(BaseModel):
    period: ReportPeriod
    metrics: ReportMetrics


# --- Periodo -------------------------------------------------------------------------------------------------------


def _next_minute(now: datetime) -> datetime:
    return now.replace(second=0, microsecond=0) + timedelta(minutes=1)


def resolve_period(
    start_date: datetime | None, end_date: datetime | None, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """`(from, to)` en UTC a partir de los parámetros opcionales (tabla del docstring del módulo)."""
    start = to_utc(start_date) if start_date is not None else None
    end = to_utc(end_date) if end_date is not None else None
    if end is None:
        end = _next_minute(to_utc(now) if now is not None else datetime.now(UTC))
    if start is None:
        start = end - DEFAULT_PERIOD
    if start >= end:
        field = "start_date" if start_date is not None else "end_date"
        raise PeriodError(field, "start_date debe ser anterior a end_date (o al momento actual si falta end_date).")
    if end - start > MAX_PERIOD:
        raise PeriodError("start_date", f"El periodo no puede superar {MAX_PERIOD.days} días.")
    return start, end


# --- Caché y cálculo -----------------------------------------------------------------------------------------------

report_cache = register(TTLCache("telemetry.report", REPORT_TTL_SECONDS, TelemetryReport))


class _KeyLock:
    """Candado de una clave. Envuelto en una clase porque `threading.Lock` no admite referencias débiles."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self) -> None:
        self.lock = threading.Lock()


_key_locks: "weakref.WeakValueDictionary[Hashable, _KeyLock]" = weakref.WeakValueDictionary()
_key_locks_guard = threading.Lock()


@contextmanager
def _locked(key: Hashable) -> Iterator[None]:
    """Exclusión por clave. El candado desaparece solo cuando nadie lo usa (sin crecer con cada periodo pedido)."""
    with _key_locks_guard:
        holder = _key_locks.get(key)
        if holder is None:
            holder = _KeyLock()
            _key_locks[key] = holder
    with holder.lock:
        yield


def cache_key(start: datetime, end: datetime) -> tuple[str, str, str]:
    """Origen de los datos y periodo en UTC. No se escribe en el log (la URL de la base lleva la contraseña)."""
    return (get_database_url(), start.isoformat(), end.isoformat())


def build_report(start: datetime, end: datetime) -> TelemetryReport:
    """Ejecuta todas las métricas del pipeline para `[start, end)`. Si una falla, se propaga el error."""
    began = time.perf_counter()
    report = TelemetryReport(
        period=ReportPeriod(from_=start, to=end),
        metrics=ReportMetrics(
            events_per_day=analysis.events_per_day(start, end),
            error_rate_by_type=analysis.error_rate_by_type(start, end),
            errors_per_day=analysis.errors_per_day(start, end),
            auth_failure_rate=analysis.auth_failure_rate(start, end),
            submission_failures_by_form=analysis.submission_failures_by_form(start, end),
        ),
    )
    logger.info(
        "Reporte de telemetría calculado para [%s, %s) en %.0f ms",
        start.isoformat(),
        end.isoformat(),
        (time.perf_counter() - began) * 1000,
    )
    return report


def get_report(start: datetime, end: datetime) -> TelemetryReport:
    """Reporte de `[start, end)` (UTC): de la caché si sigue vigente; si no, se calcula una sola vez y se guarda."""
    key = cache_key(start, end)
    with _locked(key):
        return report_cache.get_or_load(key, lambda: build_report(start, end))
