"""Análisis técnico de la telemetría con Pandas: métricas operacionales de `telemetry_events` (solo lectura).

Documentación: `docs/telemetry/telemetry-report.md`. Lo expone `GET /telemetry/report` (`app/telemetry/report.py`).

Cada métrica es una función independiente que recibe el periodo `[start, end)` y sigue siempre el mismo orden:

1. **SQL** (`load_events`): solo las columnas necesarias y solo las filas del periodo —`timestamp >= start AND
   timestamp < end`, inicio inclusivo y fin exclusivo— y, cuando la métrica lo necesita, `event_type IN (…)`. Los
   índices B-tree de `timestamp` y `event_type` (migración) sirven ambos filtros: nunca se carga la tabla entera.
2. **Pandas**: dimensiones de `tags` (`Series.str.get`, que da nulo si falta la clave o `tags` no es un objeto),
   `pd.to_datetime(..., utc=True)` antes de agrupar, `groupby()` y agregación vectorizada (`size`, `sum`, `agg`).
3. **Salida**: `list[dict]` con tipos nativos de Python (fechas como texto `YYYY-MM-DD`, nulos como `None`, nunca
   `NaN`), en orden determinista.

Ninguna función aplica una segunda ventana temporal en Pandas ni tiene un periodo por defecto: el periodo lo resuelve
el endpoint. Las fechas sin zona horaria se interpretan como UTC.

Clasificación de incidencias técnicas (`ERROR_EVENT_TYPES`): un evento es una incidencia por su `event_type`, según el
catálogo (`docs/telemetry/event-schemas.json`), no porque su nombre contenga «error» o «failed». La usan igual
`error_rate_by_type` y `errors_per_day`. Quedan fuera los rechazos de negocio (`direct_stock_edit_rejected`,
`inventory_order_rejected`, `product_duplicate_rejected`: el sistema funciona al rechazarlos) y `form_submitted`, cuyo
`outcome` de error repite incidencias ya contadas (un 401 del login es también un `login_failed`).
"""

import logging
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.telemetry.storage import telemetry_engine, telemetry_events

logger = logging.getLogger("trackflow.telemetry.analysis")

# event_type → (categoría, clave de `tags` con el motivo, o None si el catálogo no define uno).
ERROR_EVENT_TYPES: dict[str, tuple[str, str | None]] = {
    "login_failed": ("authentication", "failure_reason"),
    "access_token_rejected": ("authentication", "rejection_reason"),
    "authorization_denied": ("authorization", "reason"),
    "form_validation_failed": ("validation", None),
    "inventory_order_validation_failed": ("validation", None),
    "product_validation_failed": ("validation", None),
    "frontend_error_captured": ("frontend", "error_kind"),
    "backend_request_failed": ("api_communication", "failure_kind"),
    "api_exception_raised": ("server", "error_type"),
    "database_connection_failed": ("database", "failure_kind"),
    "telemetry_events_dropped": ("telemetry", "drop_reason"),
}

LOGIN_FAILED = "login_failed"
LOGIN_SUCCEEDED = "login_succeeded"
FORM_SUBMITTED = "form_submitted"
SUCCESS_OUTCOME = "success"

DATE_FORMAT = "%Y-%m-%d"


class TelemetryAnalysisError(Exception):
    """No se han podido leer los eventos (base caída, tabla sin crear, permisos…).

    El mensaje solo dice el tipo de error, nunca la cadena de conexión.
    """


# --- Periodo y carga (SQL) -----------------------------------------------------------------------------------------


def to_utc(value: datetime) -> datetime:
    """La misma fecha en UTC. Una fecha sin zona horaria se interpreta como UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def check_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """`(start, end)` en UTC. `ValueError` si el inicio no es anterior al fin."""
    start, end = to_utc(start), to_utc(end)
    if start >= end:
        raise ValueError("El inicio del periodo debe ser anterior al fin.")
    return start, end


def load_events(
    start: datetime,
    end: datetime,
    columns: Sequence[str],
    event_types: Iterable[str] | None = None,
    *,
    metric: str,
) -> pd.DataFrame:
    """Eventos de `[start, end)` (y de `event_types`, si se indican) con solo `columns`. Filtros en SQL.

    Devuelve un DataFrame con esas columnas aunque no haya filas.
    """
    start, end = check_period(start, end)
    table = telemetry_events
    statement = (
        select(*(table.c[name] for name in columns))
        .where(table.c.timestamp >= start, table.c.timestamp < end)
        .order_by(table.c.timestamp, table.c.id)
    )
    if event_types is not None:
        statement = statement.where(table.c.event_type.in_(sorted(set(event_types))))
    try:
        with telemetry_engine().connect() as connection:
            rows = connection.execute(statement).all()
    except SQLAlchemyError as error:
        cause = getattr(error, "orig", None) or error
        raise TelemetryAnalysisError(type(cause).__name__) from None
    logger.info("Reporte de telemetría · %s: %d filas leídas", metric, len(rows))
    return pd.DataFrame(rows, columns=list(columns))


# --- Utilidades de Pandas (vectorizadas) ---------------------------------------------------------------------------


def with_utc_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """`timestamp` como datetime UTC. Las filas con una fecha que no se puede interpretar se descartan."""
    df = df.assign(timestamp=pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="ISO8601"))
    invalid = int(df["timestamp"].isna().sum())
    if invalid:
        logger.warning("Reporte de telemetría: %d eventos con timestamp no válido descartados", invalid)
    return df.dropna(subset=["timestamp"])


def day_of(timestamps: pd.Series) -> pd.Series:
    """Día UTC de cada timestamp, como texto `YYYY-MM-DD`."""
    return timestamps.dt.strftime(DATE_FORMAT)


def period_days(start: datetime, end: datetime) -> pd.Index:
    """Días UTC que toca `[start, end)`, en orden: el índice de las series diarias (días sin eventos = 0)."""
    start, end = check_period(start, end)
    last = end - timedelta(microseconds=1)
    return pd.Index(pd.date_range(start.date(), last.date(), freq="D").strftime(DATE_FORMAT), name="date")


def tag(df: pd.DataFrame, key: str) -> pd.Series:
    """`tags[key]` de cada fila; nulo si falta la clave o `tags` no es un objeto JSON."""
    return df["tags"].str.get(key)


def text_or_null(values: pd.Series) -> pd.Series:
    """Deja solo los valores de texto; cualquier otro (número, lista, objeto mal formado) pasa a nulo."""
    return values.where(values.map(type).eq(str))


def tag_by_event_type(df: pd.DataFrame, key_by_type: dict[str, str | None]) -> pd.Series:
    """Valor de `tags[k]` donde la clave `k` depende del `event_type` de la fila (nulo si no tiene clave)."""
    keys = sorted({key for key in key_by_type.values() if key})
    if df.empty or not keys:
        return pd.Series(None, index=df.index, dtype=object)
    candidates = pd.DataFrame({key: tag(df, key) for key in keys}, index=df.index).to_numpy(dtype=object)
    position = df["event_type"].map({event_type: keys.index(key) for event_type, key in key_by_type.items() if key})
    picked = candidates[np.arange(len(df)), position.fillna(0).astype(int).to_numpy()]
    return pd.Series(picked, index=df.index, dtype=object).where(position.notna())


def percentage(part: pd.Series, total: pd.Series | int) -> pd.Series:
    """`part / total × 100` con dos decimales; nulo (nunca una división entre cero) si el total es 0."""
    total = pd.Series(total, index=part.index) if not isinstance(total, pd.Series) else total
    return (part / total.where(total > 0) * 100).round(2)


def records(df: pd.DataFrame) -> list[dict]:
    """Filas como diccionarios con tipos nativos de Python y `None` en lugar de `NaN`."""
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


# --- Métricas ------------------------------------------------------------------------------------------------------


def events_per_day(start: datetime, end: datetime) -> list[dict]:
    """¿Cuántos eventos registra el sistema cada día? Todos los `event_type`, por día UTC (días sin eventos = 0).

    `[{"date": "2026-11-11", "total_events": 31}, …]`, en orden cronológico.
    """
    df = with_utc_timestamp(load_events(start, end, ["timestamp"], metric="events_per_day"))
    counts = df.groupby(day_of(df["timestamp"]).rename("date")).size()
    return records(counts.reindex(period_days(start, end), fill_value=0).reset_index(name="total_events"))


def error_rate_by_type(start: datetime, end: datetime) -> list[dict]:
    """¿Qué tipos de incidencia técnica predominan? Incidencias por categoría, `event_type` y motivo.

    `share_pct` es el porcentaje sobre el total de incidencias del periodo. `reason` sale del campo de `tags` que el
    catálogo define para ese evento (`failure_reason`, `error_kind`…), o es `None` si no hay. De más a menos frecuente.
    """
    df = load_events(start, end, ["timestamp", "event_type", "tags"], ERROR_EVENT_TYPES, metric="error_rate_by_type")
    df = with_utc_timestamp(df)
    df = df.assign(
        error_category=df["event_type"].map({event_type: spec[0] for event_type, spec in ERROR_EVENT_TYPES.items()}),
        reason=text_or_null(
            tag_by_event_type(df, {event_type: spec[1] for event_type, spec in ERROR_EVENT_TYPES.items()})
        ),
    )
    grouped = df.groupby(["error_category", "event_type", "reason"], dropna=False).size().reset_index(name="errors")
    grouped["share_pct"] = percentage(grouped["errors"], int(grouped["errors"].sum()))
    grouped = grouped.sort_values(
        ["errors", "error_category", "event_type", "reason"], ascending=[False, True, True, True], na_position="last"
    )
    return records(grouped[["error_category", "event_type", "reason", "errors", "share_pct"]])


def errors_per_day(start: datetime, end: datetime) -> list[dict]:
    """¿Cómo evoluciona el volumen de incidencias técnicas? Mismos `event_type` que `error_rate_by_type`, por día UTC
    (días sin incidencias = 0). `[{"date": "2026-11-11", "errors": 2}, …]`, en orden cronológico.
    """
    df = with_utc_timestamp(load_events(start, end, ["timestamp"], ERROR_EVENT_TYPES, metric="errors_per_day"))
    counts = df.groupby(day_of(df["timestamp"]).rename("date")).size()
    return records(counts.reindex(period_days(start, end), fill_value=0).reset_index(name="errors"))


def auth_failure_rate(start: datetime, end: datetime) -> list[dict]:
    """¿Qué porcentaje de los inicios de sesión falla? Por día UTC: `failed / (failed + succeeded) × 100`.

    Solo los días con algún intento (sin intentos no hay tasa). `failure_rate_pct` es `None` si no hubiera intentos.
    """
    df = load_events(
        start, end, ["timestamp", "event_type"], [LOGIN_FAILED, LOGIN_SUCCEEDED], metric="auth_failure_rate"
    )
    df = with_utc_timestamp(df)
    df = df.assign(
        date=day_of(df["timestamp"]),
        failed=df["event_type"].eq(LOGIN_FAILED).astype(int),
        succeeded=df["event_type"].eq(LOGIN_SUCCEEDED).astype(int),
    )
    daily = df.groupby("date").agg(failed=("failed", "sum"), succeeded=("succeeded", "sum")).reset_index()
    daily["attempts"] = daily["failed"] + daily["succeeded"]
    daily["failure_rate_pct"] = percentage(daily["failed"], daily["attempts"])
    return records(daily.sort_values("date")[["date", "failed", "succeeded", "attempts", "failure_rate_pct"]])


def submission_failures_by_form(start: datetime, end: datetime) -> list[dict]:
    """¿Qué formularios (y, por tanto, qué llamadas a la API) concentran los envíos fallidos?

    Sobre `form_submitted`, que el backoffice emite con la respuesta de la API: un envío falla si su `outcome` existe
    y no es `success` (401, 422, otro 4xx, 5xx o sin conexión). Un envío sin `outcome` cuenta como envío pero no como
    fallo; uno sin `form_id` se agrupa en `form_id = None`. Del formulario con más fallos al que menos.
    """
    df = with_utc_timestamp(
        load_events(start, end, ["timestamp", "tags"], [FORM_SUBMITTED], metric="submission_failures_by_form")
    )
    outcome = text_or_null(tag(df, "outcome"))
    df = df.assign(
        form_id=text_or_null(tag(df, "form_id")), failed=(outcome.notna() & outcome.ne(SUCCESS_OUTCOME)).astype(int)
    )
    forms = (
        df.groupby("form_id", dropna=False).agg(submissions=("failed", "size"), failed=("failed", "sum")).reset_index()
    )
    forms["failure_rate_pct"] = percentage(forms["failed"], forms["submissions"])
    forms = forms.sort_values(["failed", "submissions", "form_id"], ascending=[False, False, True], na_position="last")
    return records(forms[["form_id", "submissions", "failed", "failure_rate_pct"]])
