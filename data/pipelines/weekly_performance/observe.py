"""observe: señales para distinguir actividad cero, captura caída y pérdida de mediciones (PIPELINE_DESIGN §9).

Solo lee (transacciones `READ ONLY`). Es una etapa **no crítica**: si falla, lanza la excepción y el flow de
`pipeline.py`, que la invoca con `return_state=True`, decide continuar con el aviso `observability_unavailable` y
marcar la ejecución como parcial. El reporte se carga igual.

- **Salud del origen** (`source_health`): eventos de *cualquier* tipo y sesiones distintas por día UTC del entorno, y
  días sin ningún evento. Si el sistema registra logins y navegación pero ninguna orden, la actividad de órdenes es
  cero de verdad; si no registra nada en absoluto, lo probable es que la captura esté caída.
- **Cobertura de la captura** (`capture_coverage`): órdenes guardadas en el inventario (`stock_entries`,
  `stock_exits` de tipo `dispatch`, la fuente de verdad) frente a eventos `inbound_order_created` /
  `outbound_order_created` capturados, por semana y almacén. Menos eventos que órdenes = mediciones perdidas; más =
  duplicadas. Así una caída del volumen se lee como «el negocio bajó» solo si las órdenes también bajaron.

Avisos (`warnings`, códigos estables): `no_events_in_window`, `silent_days`, `capture_gap`, `observability_unavailable`.
"""

import logging
from datetime import timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.inventory_models import StockEntry, StockExit
from app.reporting.tables import storage_error
from app.reporting.weeks import WeekWindow
from app.telemetry.identifiers import WAREHOUSES
from app.telemetry.storage import telemetry_engine, telemetry_events
from data.process.weekly_performance.aggregate import week_start_series
from data.process.weekly_performance.events import INBOUND, OUTBOUND

logger = logging.getLogger("trackflow.reporting.observe")


def _read_only(engine, statement) -> list:
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(postgresql_readonly=True)
            with connection.begin():
                return connection.execute(statement).all()
    except SQLAlchemyError as error:
        raise storage_error(error) from None


def _days(window: WeekWindow) -> list[str]:
    return [(window.first + timedelta(days=n)).isoformat() for n in range(len(window.weeks) * 7)]


def source_health(window: WeekWindow, environment: str) -> dict[str, Any]:
    """Eventos y sesiones por día UTC (todos los tipos del entorno) y días sin ningún evento."""
    table = telemetry_events
    rows = _read_only(
        telemetry_engine(),
        select(table.c.timestamp, table.c.session_id).where(
            table.c.environment == environment, table.c.timestamp >= window.start, table.c.timestamp < window.end
        ),
    )
    df = pd.DataFrame(rows, columns=["timestamp", "session_id"])
    day = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%d")
    days = _days(window)
    events = df.groupby(day).size().reindex(days, fill_value=0)
    sessions = df.assign(day=day).dropna(subset=["session_id"]).groupby("day")["session_id"].nunique()
    sessions = sessions.reindex(days, fill_value=0)
    return {
        "events_by_day": {d: int(n) for d, n in events.items()},
        "sessions_by_day": {d: int(n) for d, n in sessions.items()},
        "silent_days": [d for d, n in events.items() if n == 0],
        "total_events": int(events.sum()),
    }


def _recorded_orders(model, window: WeekWindow, **filters) -> pd.DataFrame:
    statement = select(model.warehouse, model.created_at).where(
        model.created_at >= window.start, model.created_at < window.end
    )
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    df = pd.DataFrame(_read_only(get_engine(), statement), columns=["warehouse", "created_at"])
    return df.assign(warehouse=df["warehouse"].map(WAREHOUSES), timestamp=pd.to_datetime(df["created_at"], utc=True))


COVERAGE_COLUMNS = ("inbound_orders", "inbound_events", "outbound_orders", "outbound_events")
_KEYS = ["week_start", "warehouse"]


def _per_week(df: pd.DataFrame, name: str) -> pd.Series:
    """Recuento por semana y almacén (índice vacío con los mismos niveles si no hay filas)."""
    if df.empty:
        return pd.Series(dtype="int64", name=name, index=pd.MultiIndex.from_tuples([], names=_KEYS))
    return df.assign(week_start=week_start_series(df["timestamp"])).groupby(_KEYS).size().rename(name)


def capture_coverage(window: WeekWindow, raw: pd.DataFrame) -> list[dict[str, Any]]:
    """Órdenes del inventario frente a eventos capturados (antes de validar), por semana y almacén."""
    events = raw.assign(
        timestamp=pd.to_datetime(raw["timestamp"], utc=True, errors="coerce"),
        warehouse=raw["tags"].map(lambda tags: tags.get("warehouse") if isinstance(tags, dict) else None),
    ).dropna(subset=["timestamp"])
    table = pd.concat(
        [
            _per_week(_recorded_orders(StockEntry, window), "inbound_orders"),
            _per_week(events[events["event_type"].eq(INBOUND)], "inbound_events"),
            _per_week(_recorded_orders(StockExit, window, exit_type="dispatch"), "outbound_orders"),
            _per_week(events[events["event_type"].eq(OUTBOUND)], "outbound_events"),
        ],
        axis=1,
    )
    if table.empty:
        return []
    table = table.reindex(columns=list(COVERAGE_COLUMNS)).fillna(0).astype("int64").reset_index().sort_values(_KEYS)
    return [
        {
            "week_start": row["week_start"].isoformat(),
            "warehouse": row["warehouse"],
            **{column: int(row[column]) for column in COVERAGE_COLUMNS},
        }
        for row in table.to_dict(orient="records")
        if row["week_start"] in window.weeks
    ]


UNAVAILABLE = "observability_unavailable"


def observe(window: WeekWindow, environment: str, raw: pd.DataFrame) -> dict[str, Any]:
    """Señales del origen y avisos. Si una señal no se puede calcular, lanza la excepción (la gestiona el flow)."""
    warnings: list[str] = []
    result: dict[str, Any] = {}
    health = source_health(window, environment)
    coverage = capture_coverage(window, raw)
    if health["total_events"] == 0:
        warnings.append("no_events_in_window")
    elif health["silent_days"]:
        warnings.append("silent_days")
    gaps = [
        row
        for row in coverage
        if row["inbound_orders"] != row["inbound_events"] or row["outbound_orders"] != row["outbound_events"]
    ]
    if gaps:
        warnings.append("capture_gap")
    result.update(source_health=health, capture_coverage=coverage, warnings=warnings)
    if warnings:
        logger.warning("Pipeline semanal · observe: avisos %s", warnings)
    return result
