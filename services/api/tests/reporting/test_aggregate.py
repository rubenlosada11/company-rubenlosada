"""Subflow aggregate: grano, fórmulas de los KPIs y semana ISO (`app/reporting/aggregate.py`, PIPELINE_DESIGN §6.4).

Ejecutar desde services/api: uv run pytest tests/reporting/test_aggregate.py
"""

from datetime import timedelta

from app.reporting.aggregate import ROW_COLUMNS, aggregate_rows
from app.reporting.validate import validate_events
from app.reporting.weeks import WeekWindow
from tests.reporting.helpers import CURRENT, DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT, W0, W1, W2, at, event, frame

WINDOW = WeekWindow(first=W1, last=W2)


def rows_for(*events, window=WINDOW):
    return aggregate_rows(validate_events(frame(*events)).valid, window)


def test_one_row_with_the_four_kpis():
    rows = rows_for(
        event(INBOUND, at(W2), quantity=300, order_id=1),
        event(INBOUND, at(W2 + timedelta(days=2)), quantity=120, order_id=2),
        *(event(OUTBOUND, at(W2, 8 + n), order_id=10 + n) for n in range(4)),
        event(STOCKOUT, at(W2)),
        event(DISCREPANCY, at(W2)),
    )
    assert rows == [
        {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "week_start": W2,
            "inbound_units_count": 420,
            "outbound_orders_count": 4,
            "stockout_events_count": 1,
            "discrepancy_events_count": 1,
            "discrepancy_rate": 0.25,
        }
    ]
    assert list(rows[0]) == ROW_COLUMNS


def test_outbound_counts_orders_not_units():
    rows = rows_for(event(OUTBOUND, at(W2), quantity=50, order_id=1), event(OUTBOUND, at(W2), quantity=7, order_id=2))
    assert rows[0]["outbound_orders_count"] == 2 and rows[0]["inbound_units_count"] == 0


def test_rate_is_zero_without_outbound_orders_and_the_count_still_shows_the_problem():
    (row,) = rows_for(event(DISCREPANCY, at(W2)), event(DISCREPANCY, at(W2)))
    assert row["outbound_orders_count"] == 0
    assert row["discrepancy_events_count"] == 2
    assert row["discrepancy_rate"] == 0.0


def test_rate_can_exceed_one():
    (row,) = rows_for(event(OUTBOUND, at(W2), order_id=1), event(DISCREPANCY, at(W2)), event(DISCREPANCY, at(W2)))
    assert row["discrepancy_rate"] == 2.0


def test_rate_is_rounded_to_four_decimals():
    events = [event(OUTBOUND, at(W2), order_id=n) for n in range(1, 981)]
    (row,) = rows_for(*events, event(DISCREPANCY, at(W2)), event(DISCREPANCY, at(W2)))
    assert row["outbound_orders_count"] == 980
    assert row["discrepancy_rate"] == 0.002  # 2 / 980 = 0.00204…, el ejemplo del BRIEFING


def test_each_row_belongs_to_a_single_client_and_warehouse():
    rows = rows_for(
        event(OUTBOUND, at(W2), client_id="fashion-co", order_id=1),
        event(OUTBOUND, at(W2), client_id="electro-brand", order_id=2),
        event(OUTBOUND, at(W2), warehouse="zaragoza", client_id="fashion-co", order_id=3),
    )
    assert [(row["warehouse"], row["client_id"]) for row in rows] == [
        ("los_angeles", "electro-brand"),
        ("los_angeles", "fashion-co"),
        ("zaragoza", "fashion-co"),
    ]
    assert all(row["outbound_orders_count"] == 1 for row in rows)


def test_week_boundary_sunday_night_and_monday_midnight():
    rows = rows_for(
        event(OUTBOUND, at(W2 - timedelta(days=1), 23, 59, 59), order_id=1),  # domingo de W1
        event(OUTBOUND, at(W2, 0, 0, 0), order_id=2),  # lunes 00:00 de W2
    )
    assert [(row["week_start"], row["outbound_orders_count"]) for row in rows] == [(W1, 1), (W2, 1)]


def test_rows_are_ordered_by_week_warehouse_and_client():
    rows = rows_for(
        event(OUTBOUND, at(W2), warehouse="zaragoza", order_id=1),
        event(OUTBOUND, at(W1), client_id="zeta", order_id=2),
        event(OUTBOUND, at(W1), client_id="alfa", order_id=3),
    )
    assert [(row["week_start"], row["client_id"], row["warehouse"]) for row in rows] == [
        (W1, "alfa", "los_angeles"),
        (W1, "zeta", "los_angeles"),
        (W2, "fashion-co", "zaragoza"),
    ]


def test_combinations_without_activity_have_no_row():
    rows = rows_for(event(OUTBOUND, at(W2), order_id=1))
    assert [row["week_start"] for row in rows] == [W2]  # W1 sin eventos: sin filas inventadas


def test_events_outside_the_window_are_dropped():
    rows = rows_for(event(OUTBOUND, at(W0), order_id=1), event(OUTBOUND, at(CURRENT), order_id=2))
    assert rows == []


def test_native_python_types():
    (row,) = rows_for(event(INBOUND, at(W2), quantity=3, order_id=1))
    assert {type(value) for key, value in row.items() if key.endswith("_count")} == {int}
    assert type(row["discrepancy_rate"]) is float and type(row["warehouse"]) is str


def test_no_events_no_rows():
    assert rows_for() == []
