"""aggregate: filas del reporte a partir de los eventos válidos (PIPELINE_DESIGN.md §6.4).

Grano: una fila por `(warehouse, client_id, week_start)` con al menos un evento en la semana. Cada fila es de un
único cliente; las combinaciones sin actividad no tienen fila.

| Columna | Cálculo |
| --- | --- |
| `inbound_units_count` | suma de `quantity` de `inbound_order_created` |
| `outbound_orders_count` | número de `outbound_order_created` |
| `stockout_events_count` | número de `stock_threshold_triggered` |
| `discrepancy_events_count` | número de `inventory_discrepancy_detected` |
| `discrepancy_rate` | `discrepancy_events_count / outbound_orders_count`, 4 decimales; 0 sin pedidos (puede ser > 1) |

`week_start` es el lunes UTC de `timestamp`. Los eventos fuera de las semanas pedidas (`weeks`) se descartan (la
extracción ya filtra por fechas: es una segunda barrera). Función pura: sin base de datos ni Prefect.

Desde el Hito 6 cada KPI es una función de `kpis.py` (y una task de Prefect en el subflow de transformación):
`weekly_events` prepara los eventos y `aggregate_rows` encadena las funciones de los KPIs en un solo paso, con el
mismo resultado que el subflow.
"""

from collections.abc import Iterable
from datetime import date

import pandas as pd

from data.process.weekly_performance.kpis import (
    KEYS,
    RATE_DECIMALS,
    ROW_COLUMNS,
    build_rows,
    discrepancy_count,
    discrepancy_rate,
    inbound_volume,
    outbound_throughput,
    stockout_frequency,
)

__all__ = ["KEYS", "RATE_DECIMALS", "ROW_COLUMNS", "aggregate_rows", "week_start_series", "weekly_events"]


def week_start_series(timestamps: pd.Series) -> pd.Series:
    """Lunes (UTC, `datetime.date`) de la semana ISO de cada timestamp con zona horaria."""
    utc = timestamps.dt.tz_convert("UTC")
    return (utc.dt.normalize() - pd.to_timedelta(utc.dt.day_of_week, unit="D")).dt.date


def weekly_events(valid: pd.DataFrame, weeks: Iterable[date]) -> pd.DataFrame:
    """Eventos válidos con su `week_start` (lunes UTC), solo los de las semanas `weeks`."""
    if valid.empty:
        return valid.assign(week_start=pd.Series([], dtype=object)).reset_index(drop=True)
    df = valid.assign(week_start=week_start_series(valid["timestamp"]))
    return df[df["week_start"].isin(list(weeks))].reset_index(drop=True)


def aggregate_rows(valid: pd.DataFrame, weeks: Iterable[date]) -> list[dict]:
    """Filas del reporte de las semanas `weeks` (lunes), ordenadas por semana, almacén y cliente, con tipos nativos."""
    events = weekly_events(valid, weeks)
    if events.empty:
        return []
    outbound = outbound_throughput(events)
    discrepancies = discrepancy_count(events)
    return build_rows(
        inbound_volume(events),
        outbound,
        stockout_frequency(events),
        discrepancies,
        discrepancy_rate(discrepancies, outbound),
    )
