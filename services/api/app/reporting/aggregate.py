"""Subflow 3 · aggregate: filas del reporte a partir de los eventos válidos (PIPELINE_DESIGN.md §6.4).

Grano: una fila por `(warehouse, client_id, week_start)` con al menos un evento en la semana. Cada fila es de un
único cliente; las combinaciones sin actividad no tienen fila.

| Columna | Cálculo |
| --- | --- |
| `inbound_units_count` | suma de `quantity` de `inbound_order_created` |
| `outbound_orders_count` | número de `outbound_order_created` |
| `stockout_events_count` | número de `stock_threshold_triggered` |
| `discrepancy_events_count` | número de `inventory_discrepancy_detected` |
| `discrepancy_rate` | `discrepancy_events_count / outbound_orders_count`, 4 decimales; 0 sin pedidos (puede ser > 1) |

`week_start` es el lunes UTC de `timestamp`. Los eventos fuera de las semanas de la ventana se descartan (la extracción
ya filtra por fechas: es una segunda barrera). Sin tocar la base.
"""

import pandas as pd

from app.reporting.extract import DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT
from app.reporting.weeks import WeekWindow

KEYS = ["warehouse", "client_id", "week_start"]
COUNT_COLUMNS = {
    OUTBOUND: "outbound_orders_count",
    STOCKOUT: "stockout_events_count",
    DISCREPANCY: "discrepancy_events_count",
}
RATE_DECIMALS = 4
ROW_COLUMNS = [
    *KEYS,
    "inbound_units_count",
    "outbound_orders_count",
    "stockout_events_count",
    "discrepancy_events_count",
    "discrepancy_rate",
]


def week_start_series(timestamps: pd.Series) -> pd.Series:
    """Lunes (UTC, `datetime.date`) de la semana ISO de cada timestamp con zona horaria."""
    utc = timestamps.dt.tz_convert("UTC")
    return (utc.dt.normalize() - pd.to_timedelta(utc.dt.day_of_week, unit="D")).dt.date


def aggregate_rows(valid: pd.DataFrame, window: WeekWindow) -> list[dict]:
    """Filas del reporte, ordenadas por semana, almacén y cliente, con tipos nativos de Python."""
    if valid.empty:
        return []
    df = valid.assign(week_start=week_start_series(valid["timestamp"]))
    df = df[df["week_start"].isin(window.weeks)]
    if df.empty:
        return []

    grouped = df.groupby(KEYS)
    columns = {"inbound_units_count": df[df["event_type"].eq(INBOUND)].groupby(KEYS)["quantity"].sum()}
    for event_type, column in COUNT_COLUMNS.items():
        columns[column] = df[df["event_type"].eq(event_type)].groupby(KEYS).size()
    table = (
        pd.DataFrame(columns, index=grouped.size().index).reindex(columns=ROW_COLUMNS[3:-1]).fillna(0).astype("int64")
    )

    outbound = table["outbound_orders_count"]
    table["discrepancy_rate"] = (
        (table["discrepancy_events_count"] / outbound.where(outbound > 0)).round(RATE_DECIMALS).fillna(0.0)
    )
    table = table.reset_index().sort_values(["week_start", "warehouse", "client_id"], kind="stable")
    return [
        {
            "warehouse": str(row.warehouse),
            "client_id": str(row.client_id),
            "week_start": row.week_start,
            "inbound_units_count": int(row.inbound_units_count),
            "outbound_orders_count": int(row.outbound_orders_count),
            "stockout_events_count": int(row.stockout_events_count),
            "discrepancy_events_count": int(row.discrepancy_events_count),
            "discrepancy_rate": float(row.discrepancy_rate),
        }
        for row in table[ROW_COLUMNS].itertuples(index=False)
    ]
