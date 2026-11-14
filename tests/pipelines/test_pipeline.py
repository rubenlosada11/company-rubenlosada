"""Tests unitarios de las tasks de KPI del pipeline de desempeño (Hito 6, PIPELINE_DESIGN.md §19.6).

Prueban las tasks de transformación de `data/pipelines/pipeline.py` llamando a su cuerpo (`task.fn(...)`): la lógica de
negocio, sin el motor de Prefect, sin servidor de Prefect, sin base de datos y sin red. Los eventos se construyen en
memoria con la forma real de una fila de `telemetry_events` (`id`, `event_type`, `timestamp`, `tags`), tal como los
entrega la extracción.

Ejecución, desde la raíz del monorepo (Prefect y Pandas están en el entorno de `services/api`):

    uv run --project services/api python -m pytest tests/pipelines/test_pipeline.py -v

o, con `services\\api\\.venv` activado: `python -m pytest tests/pipelines/test_pipeline.py -v`.

Datos de referencia: semana ISO del lunes 2026-11-02 (`WEEK`, del lunes 00:00 al domingo 23:59:59 UTC).

| Almacén / cliente | Entradas (unidades) | Pedidos de salida | Quiebres | Discrepancias |
| --- | --- | --- | --- | --- |
| los_angeles / fashion-co | 120 + 80 + 5 = **205** | 4 (de 10, 25, 1 y 300 unidades) | 0 | 1 |
| los_angeles / tech-gear | 50 | 0 | 2 (+1 del lunes siguiente, fuera) | 1 |
| zaragoza / fashion-co | 30 | 2 | 0 | 3 |

Además hay una entrada de 1.000 unidades el lunes siguiente a las 00:00:00 UTC (otra semana: no cuenta).
"""

import socket
import uuid
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from data.pipelines import pipeline
from data.process.weekly_performance.events import DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT
from data.process.weekly_performance.kpis import KpiInputError
from data.process.weekly_performance.transform import fingerprint_events, transform_events
from data.process.weekly_performance.validate import SourceSchemaError

WEEK = date(2026, 11, 2)  # lunes
NEXT_WEEK = date(2026, 11, 9)
LA, ZGZ = "los_angeles", "zaragoza"
FASHION, TECH = "fashion-co", "tech-gear"


# --- Fixtures ----------------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_infrastructure(monkeypatch):
    """Aislamiento: cualquier intento de usar la red (Supabase, HTTP, servidor de Prefect) o la E/S del pipeline falla.

    Si un test dependiera de la base de datos o de un servicio externo, este fixture lo haría fallar en lugar de dejarlo
    pasar contra lo que hubiera en la máquina.
    """

    def blocked(*args, **kwargs):
        raise AssertionError("Un test unitario no puede usar la red, la base de datos ni el servidor de Prefect.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for name in ("extract_events", "load_rows", "observe", "write_snapshot"):
        monkeypatch.setattr(pipeline, name, blocked)
    for name in ("start_run", "finish_run", "set_phase", "get_run"):
        monkeypatch.setattr(pipeline.runs, name, blocked)


def at(day: date, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


def telemetry_event(
    event_type: str,
    timestamp,
    *,
    warehouse=LA,
    client_id=FASHION,
    quantity=1,
    order_id: int | None = None,
) -> dict:
    """Fila de `telemetry_events` con las propiedades de `tags` del contrato de telemetría."""
    tags = {
        "warehouse": warehouse,
        "client_id": client_id,
        "product_id": "SKU-1",
        "product_category": "fashion",
        "quantity": quantity,
    }
    if order_id is not None:
        tags["order_id"] = order_id
    return {"id": uuid.uuid4(), "event_type": event_type, "timestamp": timestamp, "tags": tags}


def extraction_of(*events: dict) -> pipeline.Extraction:
    """Lo que devuelve el subflow de extracción, construido en memoria."""
    frame = pd.DataFrame(list(events), columns=["id", "event_type", "timestamp", "tags"])
    return pipeline.Extraction(events=frame, environment="development", fingerprint=fingerprint_events(frame))


@pytest.fixture
def week_events() -> list[dict]:
    """Eventos de la tabla del docstring: valores conocidos con resultados calculados a mano."""
    sunday_last_second = at(date(2026, 11, 8), 23, 59, 59)
    next_monday_first_second = at(NEXT_WEEK, 0, 0, 0)
    return [
        # Volumen de entrada
        telemetry_event(INBOUND, at(WEEK, 9), quantity=120, order_id=1),
        telemetry_event(INBOUND, at(date(2026, 11, 4)), quantity=80, order_id=2),
        telemetry_event(INBOUND, sunday_last_second, quantity=5, order_id=3),  # aún es la semana WEEK
        telemetry_event(INBOUND, at(WEEK), client_id=TECH, quantity=50, order_id=4),
        telemetry_event(INBOUND, at(WEEK), warehouse=ZGZ, quantity=30, order_id=5),
        telemetry_event(INBOUND, next_monday_first_second, quantity=1000, order_id=6),  # otra semana
        # Throughput de salida: se cuentan pedidos, no unidades
        *(telemetry_event(OUTBOUND, at(WEEK, 8 + n), quantity=q, order_id=100 + n) for n, q in enumerate((10, 25, 1, 300))),
        *(telemetry_event(OUTBOUND, at(WEEK, 10 + n), warehouse=ZGZ, order_id=200 + n) for n in range(2)),
        # Frecuencia de quiebre de stock
        telemetry_event(STOCKOUT, at(date(2026, 11, 3)), client_id=TECH),
        telemetry_event(STOCKOUT, sunday_last_second, client_id=TECH),
        telemetry_event(STOCKOUT, next_monday_first_second, client_id=TECH),  # otra semana
        # Discrepancias (numerador de la tasa)
        telemetry_event(DISCREPANCY, at(WEEK, 18)),
        telemetry_event(DISCREPANCY, at(WEEK, 18), client_id=TECH),
        *(telemetry_event(DISCREPANCY, at(date(2026, 11, 5), 9 + n), warehouse=ZGZ) for n in range(3)),
    ]


@pytest.fixture
def prepared(week_events) -> pipeline.PreparedEvents:
    """Salida de la task `prepare-weekly-events` (validate + semana ISO) para la semana WEEK."""
    return pipeline.prepare_task.fn(extraction_of(*week_events), [WEEK])


def as_dict(series: pd.Series) -> dict[tuple[str, str, date], float]:
    return {key: value for key, value in series.items()}


# --- Test 1 · Volumen de entrada ---------------------------------------------------------------------------------------


def test_inbound_volume_sums_units_received_per_warehouse_client_and_week(prepared):
    """KPI «Volumen de entrada» = suma de `quantity` de `inbound_order_created` de la semana.

    Cálculo manual: los_angeles/fashion-co recibe 120 (lunes) + 80 (miércoles) + 5 (domingo 23:59:59, todavía la misma
    semana ISO) = 205 unidades. Las 1.000 unidades del lunes siguiente a las 00:00:00 son de otra semana y no cuentan.
    """
    volume = pipeline.inbound_volume_task.fn(prepared.events)
    assert as_dict(volume) == {
        (LA, FASHION, WEEK): 205,
        (LA, TECH, WEEK): 50,
        (ZGZ, FASHION, WEEK): 30,
    }


# --- Test 2 · Throughput de salida -------------------------------------------------------------------------------------


def test_outbound_throughput_counts_orders_not_units(prepared):
    """KPI «Throughput de salida» = número de `outbound_order_created` de la semana.

    Cálculo manual: los_angeles/fashion-co despacha 4 pedidos (de 10, 25, 1 y 300 unidades: 336 unidades, pero el KPI
    cuenta pedidos → 4); zaragoza/fashion-co, 2. tech-gear no despacha nada: no aparece (no se inventan ceros).
    """
    throughput = pipeline.outbound_throughput_task.fn(prepared.events)
    assert as_dict(throughput) == {(LA, FASHION, WEEK): 4, (ZGZ, FASHION, WEEK): 2}


# --- Test 3 · Frecuencia de quiebre de stock ---------------------------------------------------------------------------


def test_stockout_frequency_counts_threshold_events_inside_the_iso_week(prepared):
    """KPI «Frecuencia de quiebre de stock» = número de `stock_threshold_triggered` de la semana.

    Cálculo manual: los_angeles/tech-gear tiene 3 eventos: martes, domingo 23:59:59 (cuenta) y lunes siguiente 00:00:00
    (semana siguiente, no cuenta) → 2. La semana es [lunes 00:00, lunes siguiente 00:00) en UTC.
    """
    stockouts = pipeline.stockout_frequency_task.fn(prepared.events)
    assert as_dict(stockouts) == {(LA, TECH, WEEK): 2}


# --- Test 4 · Tasa de discrepancia -------------------------------------------------------------------------------------


def test_discrepancy_rate_divides_discrepancies_by_outbound_orders(prepared):
    """KPI «Tasa de discrepancia» = discrepancias / pedidos de salida de la semana; 0 si no hubo pedidos.

    Cálculo manual:
    - los_angeles/fashion-co: 1 discrepancia / 4 pedidos = 0,25.
    - zaragoza/fashion-co: 3 / 2 = 1,5 → puede superar 1 (señal fuerte, no un error).
    - los_angeles/tech-gear: 1 discrepancia / 0 pedidos → 0 por definición del BRIEFING (sin división por cero); el
      conteo de apoyo (1) sigue mostrando el problema.
    """
    discrepancies = pipeline.discrepancy_count_task.fn(prepared.events)
    outbound = pipeline.outbound_throughput_task.fn(prepared.events)
    assert as_dict(discrepancies) == {(LA, FASHION, WEEK): 1, (LA, TECH, WEEK): 1, (ZGZ, FASHION, WEEK): 3}

    rate = pipeline.discrepancy_rate_task.fn(discrepancies, outbound)
    assert as_dict(rate) == {(LA, FASHION, WEEK): 0.25, (LA, TECH, WEEK): 0.0, (ZGZ, FASHION, WEEK): 1.5}


def test_discrepancy_rate_is_rounded_to_four_decimals():
    """1 / 3 = 0,333333… → 0,3333 (4 decimales, como la columna del reporte). Valores límite: 0/0 = 0 y 0/5 = 0."""
    index = pd.MultiIndex.from_tuples([(LA, FASHION, WEEK), (LA, TECH, WEEK), (ZGZ, FASHION, WEEK)])
    discrepancies = pd.Series([1, 0, 0], index=index)
    outbound = pd.Series([3, 0, 5], index=index)
    rate = pipeline.discrepancy_rate_task.fn(discrepancies, outbound)
    assert rate.tolist() == [0.3333, 0.0, 0.0]


# --- Test 5 · Comportamiento defensivo con datos mal formados ----------------------------------------------------------


def test_malformed_events_are_excluded_and_counted_and_the_kpi_uses_the_rest():
    """Comportamiento definido (PIPELINE_DESIGN §6.3): un evento mal formado se RECHAZA (no se corrige ni se imputa),
    se cuenta por tipo y motivo, y la ejecución sigue con los válidos.

    Entrada: 1 entrada válida de 10 unidades y 4 inválidas (timestamp no interpretable, almacén nulo, cantidad de texto
    «7», cliente que no es un slug). Resultado: volumen = 10 (solo la válida) y un rechazo por cada motivo.
    """
    extraction = extraction_of(
        telemetry_event(INBOUND, at(WEEK), quantity=10, order_id=1),
        telemetry_event(INBOUND, "ayer por la tarde", quantity=500, order_id=2),
        telemetry_event(INBOUND, at(WEEK), warehouse=None, quantity=500, order_id=3),
        telemetry_event(INBOUND, at(WEEK), quantity="7", order_id=4),
        telemetry_event(INBOUND, at(WEEK), client_id="Fashion Co", quantity=500, order_id=5),
    )
    prepared = pipeline.prepare_task.fn(extraction, [WEEK])

    assert prepared.events_read[INBOUND] == 5
    assert prepared.rejected == {
        INBOUND: {"invalid_client_id": 1, "invalid_quantity": 1, "invalid_timestamp": 1, "invalid_warehouse": 1}
    }
    assert as_dict(pipeline.inbound_volume_task.fn(prepared.events)) == {(LA, FASHION, WEEK): 10}


# --- Test 6 · Comportamiento defensivo con entradas que incumplen el contrato ------------------------------------------


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (lambda df: df.drop(columns=["quantity"]), "Faltan columnas en los eventos: quantity"),
        (lambda df: df.assign(quantity=df["quantity"].astype(object).where(df.index != 0, "7")), "deben ser enteros"),
        (lambda df: df.assign(quantity=df["quantity"].where(df.index != 0, 0)), "deben ser ≥ 1"),
        (lambda df: df.assign(warehouse=df["warehouse"].where(df.index != 0, None)), "valores nulos en: warehouse"),
        (lambda df: df.assign(warehouse=df["warehouse"].where(df.index != 0, "madrid")), "Almacenes no válidos: madrid"),
    ],
    ids=["sin-columna-quantity", "cantidad-texto", "cantidad-cero", "almacen-nulo", "almacen-desconocido"],
)
def test_kpi_task_rejects_input_that_breaks_its_contract(prepared, broken, message):
    """Si a una task de KPI le llega algo que `prepare-weekly-events` nunca produciría, es un error de código: la task
    lanza `KpiInputError` con el motivo concreto (y la ejecución falla sin cargar nada), en vez de calcular un número
    sobre datos que no cumplen el contrato. Se comprueba el mensaje, no «cualquier excepción»."""
    events = broken(prepared.events.copy())
    with pytest.raises(KpiInputError, match=message):
        pipeline.inbound_volume_task.fn(events)


def test_discrepancy_rate_rejects_negative_counts():
    index = pd.MultiIndex.from_tuples([(LA, FASHION, WEEK)])
    with pytest.raises(KpiInputError, match="valores negativos"):
        pipeline.discrepancy_rate_task.fn(pd.Series([-1], index=index), pd.Series([4], index=index))


def test_an_extraction_without_the_contract_columns_fails_before_computing():
    """Si la extracción no trae `tags` (fallo de la consulta, no de los datos), no se calcula nada: `SourceSchemaError`."""
    extraction = extraction_of(telemetry_event(INBOUND, at(WEEK), quantity=10, order_id=1))
    broken = pipeline.Extraction(
        events=extraction.events.drop(columns=["tags"]), environment="development", fingerprint="0" * 64
    )
    with pytest.raises(SourceSchemaError, match="Faltan columnas en la extracción: tags"):
        pipeline.prepare_task.fn(broken, [WEEK])


# --- Filas del reporte -------------------------------------------------------------------------------------------------


def test_assembled_rows_follow_the_target_table_contract_and_match_the_part_2_transformation(week_events, prepared):
    """La task final une los KPIs en las filas de `reporting.weekly_warehouse_client_performance` (una por almacén,
    cliente y semana; cada fila de un único cliente) y da exactamente lo mismo que la transformación de la Parte 2."""
    events = prepared.events
    inbound = pipeline.inbound_volume_task.fn(events)
    outbound = pipeline.outbound_throughput_task.fn(events)
    stockouts = pipeline.stockout_frequency_task.fn(events)
    discrepancies = pipeline.discrepancy_count_task.fn(events)
    rates = pipeline.discrepancy_rate_task.fn(discrepancies, outbound)
    rows = pipeline.assemble_rows_task.fn(prepared, [WEEK], inbound, outbound, stockouts, discrepancies, rates)

    assert rows == [
        {
            "warehouse": LA,
            "client_id": FASHION,
            "week_start": WEEK,
            "inbound_units_count": 205,
            "outbound_orders_count": 4,
            "stockout_events_count": 0,
            "discrepancy_events_count": 1,
            "discrepancy_rate": 0.25,
        },
        {
            "warehouse": LA,
            "client_id": TECH,
            "week_start": WEEK,
            "inbound_units_count": 50,
            "outbound_orders_count": 0,
            "stockout_events_count": 2,
            "discrepancy_events_count": 1,
            "discrepancy_rate": 0.0,
        },
        {
            "warehouse": ZGZ,
            "client_id": FASHION,
            "week_start": WEEK,
            "inbound_units_count": 30,
            "outbound_orders_count": 2,
            "stockout_events_count": 0,
            "discrepancy_events_count": 3,
            "discrepancy_rate": 1.5,
        },
    ]
    assert rows == transform_events(extraction_of(*week_events).events, [WEEK]).rows


def test_a_week_without_events_produces_no_rows():
    """Sin eventos no hay filas (no se inventan ceros); las tasks devuelven series vacías, sin error."""
    prepared = pipeline.prepare_task.fn(extraction_of(), [WEEK])
    empty = pipeline.inbound_volume_task.fn(prepared.events)
    outbound = pipeline.outbound_throughput_task.fn(prepared.events)
    discrepancies = pipeline.discrepancy_count_task.fn(prepared.events)
    rates = pipeline.discrepancy_rate_task.fn(discrepancies, outbound)
    stockouts = pipeline.stockout_frequency_task.fn(prepared.events)
    assert empty.empty and rates.empty
    assert pipeline.assemble_rows_task.fn(prepared, [WEEK], empty, outbound, stockouts, discrepancies, rates) == []
