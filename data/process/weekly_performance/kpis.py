"""KPIs del Reporte Semanal de Desempeño por Almacén y Cliente, uno por función (PIPELINE_DESIGN.md §6.4 y §19.4).

Cada función calcula **un** KPI del BRIEFING (§2) a partir de los eventos válidos de la ventana ya preparados
(`prepare_events`: validados y con su `week_start`), y devuelve una `pd.Series` indexada por
`(warehouse, client_id, week_start)` solo con las combinaciones que tienen eventos de ese tipo:

| KPI (BRIEFING §2) | Función | Cálculo por combinación |
| --- | --- | --- |
| Volumen de entrada | `inbound_volume` | suma de `quantity` de `inbound_order_created` (unidades) |
| Throughput de salida | `outbound_throughput` | número de `outbound_order_created` (pedidos, no unidades) |
| Frecuencia de quiebre de stock | `stockout_frequency` | número de `stock_threshold_triggered` |
| (apoyo de la Tasa de discrepancia) | `discrepancy_count` | número de `inventory_discrepancy_detected` |
| Tasa de discrepancia | `discrepancy_rate` | `discrepancias / pedidos`, 4 decimales; **0 sin pedidos**; puede superar 1 |

`build_rows` une las series en las filas de la tabla de destino (una por combinación con al menos un evento).

Funciones puras: sin base de datos, sin red y sin Prefect. Las tasks de `data/pipelines/pipeline.py` las envuelven y
los tests unitarios (`tests/pipelines/test_pipeline.py`) las prueban con DataFrames en memoria.

**Comportamiento defensivo.** Los eventos mal formados no deberían llegar aquí: `validate` los rechaza y los cuenta
(§6.3). Si aun así llega una entrada estructuralmente inválida (falta una columna, hay nulos en las dimensiones, un
almacén desconocido o una cantidad que no es un entero ≥ 1), es un error de código, no de datos: `KpiInputError` con
el motivo concreto, y la ejecución falla sin cargar nada (nunca se publica un KPI calculado sobre datos que no cumplen
el contrato).
"""

from datetime import date

import numpy as np
import pandas as pd

from data.process.weekly_performance.events import DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT
from data.process.weekly_performance.validate import WAREHOUSES

KEYS = ["warehouse", "client_id", "week_start"]
RATE_DECIMALS = 4
COUNT_COLUMNS = ("inbound_units_count", "outbound_orders_count", "stockout_events_count", "discrepancy_events_count")
ROW_COLUMNS = [*KEYS, *COUNT_COLUMNS, "discrepancy_rate"]
EVENT_COLUMNS = ["event_type", *KEYS]


class KpiInputError(ValueError):
    """La entrada de un KPI no cumple su contrato (columnas, nulos, almacén o cantidad). Es un error de código."""


def _check_events(events: pd.DataFrame, *, with_quantity: bool = False) -> None:
    """`KpiInputError` si `events` no tiene la forma que garantiza `prepare_events`."""
    if not isinstance(events, pd.DataFrame):
        raise KpiInputError(f"Se esperaba un DataFrame de eventos, no {type(events).__name__}.")
    required = [*EVENT_COLUMNS, "quantity"] if with_quantity else EVENT_COLUMNS
    missing = [column for column in required if column not in events.columns]
    if missing:
        raise KpiInputError(f"Faltan columnas en los eventos: {', '.join(missing)}.")
    nulls = [column for column in EVENT_COLUMNS if events[column].isna().any()]
    if nulls:
        raise KpiInputError(f"Hay valores nulos en: {', '.join(nulls)}.")
    unknown = sorted(set(events["warehouse"]) - set(WAREHOUSES))
    if unknown:
        raise KpiInputError(f"Almacenes no válidos: {', '.join(map(str, unknown))}.")


def _is_integer(value: object) -> bool:
    # `bool` es subclase de `int` en Python: `True` no es una cantidad.
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


def _empty() -> pd.Series:
    index = pd.MultiIndex.from_arrays([[], [], []], names=KEYS)
    return pd.Series([], index=index, dtype="int64")


def _count(events: pd.DataFrame, event_type: str) -> pd.Series:
    selected = events[events["event_type"].eq(event_type)]
    if selected.empty:
        return _empty()
    return selected.groupby(KEYS).size().astype("int64")


def inbound_volume(events: pd.DataFrame) -> pd.Series:
    """Volumen de entrada: unidades recibidas (suma de `quantity` de `inbound_order_created`) por combinación."""
    _check_events(events, with_quantity=True)
    inbound = events[events["event_type"].eq(INBOUND)]
    if inbound.empty:
        return _empty()
    quantity = inbound["quantity"]
    # Tipo exacto: un `"5"` de texto, un `5.5`, un nulo o un `True` no son cantidades (validate ya los rechaza).
    if not quantity.map(_is_integer).all():
        raise KpiInputError("Las cantidades de inbound_order_created deben ser enteros (no texto, decimales ni nulos).")
    if (quantity < 1).any():
        raise KpiInputError("Las cantidades de inbound_order_created deben ser ≥ 1.")
    return inbound.groupby(KEYS)["quantity"].sum().astype("int64")


def outbound_throughput(events: pd.DataFrame) -> pd.Series:
    """Throughput de salida: pedidos despachados (número de `outbound_order_created`) por combinación."""
    _check_events(events)
    return _count(events, OUTBOUND)


def stockout_frequency(events: pd.DataFrame) -> pd.Series:
    """Frecuencia de quiebre de stock: veces bajo el mínimo (número de `stock_threshold_triggered`) por combinación."""
    _check_events(events)
    return _count(events, STOCKOUT)


def discrepancy_count(events: pd.DataFrame) -> pd.Series:
    """Discrepancias detectadas (número de `inventory_discrepancy_detected`): numerador de la tasa de discrepancia."""
    _check_events(events)
    return _count(events, DISCREPANCY)


def discrepancy_rate(discrepancies: pd.Series, outbound_orders: pd.Series) -> pd.Series:
    """Tasa de discrepancia: `discrepancias / pedidos` por combinación, a 4 decimales; 0 si no hubo pedidos.

    El índice es la unión de las dos series (una combinación sin una de ellas cuenta 0). La tasa puede superar 1 (más
    discrepancias que pedidos en la semana): no es un error, es una señal fuerte (PIPELINE_DESIGN §6.4).
    """
    for name, series in (("discrepancias", discrepancies), ("pedidos", outbound_orders)):
        if not isinstance(series, pd.Series):
            raise KpiInputError(f"Se esperaba una serie de {name}, no {type(series).__name__}.")
        if (series < 0).any():
            raise KpiInputError(f"La serie de {name} tiene valores negativos.")
    index = discrepancies.index.union(outbound_orders.index)
    numerator = discrepancies.reindex(index, fill_value=0).astype("float64")
    denominator = outbound_orders.reindex(index, fill_value=0).astype("float64")
    rate = (numerator / denominator.where(denominator > 0)).round(RATE_DECIMALS).fillna(0.0)
    rate.index.names = KEYS
    return rate


def build_rows(
    inbound_units: pd.Series,
    outbound_orders: pd.Series,
    stockouts: pd.Series,
    discrepancies: pd.Series,
    rates: pd.Series,
) -> list[dict]:
    """Filas de la tabla de destino: una por combinación con algún evento, ordenadas por semana, almacén y cliente.

    Tipos nativos de Python (`int`, `float`, `date`) para la carga y el JSON.
    """
    counts = {
        "inbound_units_count": inbound_units,
        "outbound_orders_count": outbound_orders,
        "stockout_events_count": stockouts,
        "discrepancy_events_count": discrepancies,
    }
    index = None
    for series in counts.values():
        index = series.index if index is None else index.union(series.index)
    if index is None or len(index) == 0:
        return []
    table = pd.DataFrame({name: series.reindex(index, fill_value=0) for name, series in counts.items()})
    table = table.fillna(0).astype("int64")
    table["discrepancy_rate"] = rates.reindex(index, fill_value=0.0).astype("float64")
    table.index.names = KEYS
    table = table.reset_index().sort_values(["week_start", "warehouse", "client_id"], kind="stable")
    return [
        {
            "warehouse": str(row.warehouse),
            "client_id": str(row.client_id),
            "week_start": row.week_start if isinstance(row.week_start, date) else pd.Timestamp(row.week_start).date(),
            "inbound_units_count": int(row.inbound_units_count),
            "outbound_orders_count": int(row.outbound_orders_count),
            "stockout_events_count": int(row.stockout_events_count),
            "discrepancy_events_count": int(row.discrepancy_events_count),
            "discrepancy_rate": float(row.discrepancy_rate),
        }
        for row in table[ROW_COLUMNS].itertuples(index=False)
    ]
