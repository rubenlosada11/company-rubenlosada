"""Subflow load: upsert, reconciliación y transacción única (`app/reporting/load.py`, PIPELINE_DESIGN.md §8).

Ejecutar desde services/api: uv run pytest tests/reporting/test_load.py
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.reporting import load
from app.reporting.load import load_rows
from app.reporting.tables import ReportingStorageError, reporting_engine, weekly_performance
from app.reporting.weeks import WeekWindow
from tests.reporting.helpers import W0, W1, W2

WINDOW = WeekWindow(first=W1, last=W2)


def single_week(week) -> WeekWindow:
    return WeekWindow(first=week, last=week)


T1 = datetime(2026, 11, 9, 6, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)


def row(week_start, client_id="fashion-co", warehouse="los_angeles", outbound=10, discrepancies=0):
    return {
        "warehouse": warehouse,
        "client_id": client_id,
        "week_start": week_start,
        "inbound_units_count": 100,
        "outbound_orders_count": outbound,
        "stockout_events_count": 0,
        "discrepancy_events_count": discrepancies,
        "discrepancy_rate": round(discrepancies / outbound, 4) if outbound else 0.0,
    }


def stored() -> dict[tuple, dict]:
    with reporting_engine().connect() as connection:
        rows = [dict(r._mapping) for r in connection.execute(select(weekly_performance))]
    return {(r["warehouse"], r["client_id"], r["week_start"]): r for r in rows}


def test_inserts_new_rows_with_id_and_computed_at():
    result = load_rows([row(W1), row(W2, client_id="electro-brand")], WINDOW, T1)
    assert (result.rows_upserted, result.rows_deleted) == (2, 0)
    table = stored()
    assert set(table) == {("los_angeles", "fashion-co", W1), ("los_angeles", "electro-brand", W2)}
    first = table[("los_angeles", "fashion-co", W1)]
    assert first["id"] is not None and first["outbound_orders_count"] == 10
    assert first["computed_at"].replace(tzinfo=UTC) == T1


def test_upsert_updates_kpis_and_keeps_the_id():
    load_rows([row(W2)], single_week(W2), T1)
    original_id = stored()[("los_angeles", "fashion-co", W2)]["id"]
    load_rows([row(W2, outbound=20, discrepancies=1)], single_week(W2), T2)
    updated = stored()[("los_angeles", "fashion-co", W2)]
    assert updated["id"] == original_id
    assert updated["outbound_orders_count"] == 20 and updated["discrepancy_rate"] == 0.05
    assert updated["computed_at"].replace(tzinfo=UTC) == T2
    assert len(stored()) == 1  # nunca duplicados


def test_same_load_twice_leaves_the_same_table():
    rows = [row(W1), row(W2), row(W2, warehouse="zaragoza")]
    load_rows(rows, WINDOW, T1)
    first = {key: {k: v for k, v in value.items() if k != "computed_at"} for key, value in stored().items()}
    load_rows(rows, WINDOW, T2)
    second = {key: {k: v for k, v in value.items() if k != "computed_at"} for key, value in stored().items()}
    assert first == second


def test_reconciliation_removes_vanished_rows_only_inside_the_window():
    load_rows([row(W0)], single_week(W0), T1)  # semana fuera de la ventana siguiente
    load_rows([row(W1), row(W2), row(W2, client_id="electro-brand")], WINDOW, T1)
    result = load_rows([row(W2)], WINDOW, T2)  # W1 y electro-brand ya no tienen eventos
    assert result.rows_deleted == 2
    assert set(stored()) == {("los_angeles", "fashion-co", W0), ("los_angeles", "fashion-co", W2)}


def test_empty_result_clears_the_window_weeks():
    load_rows([row(W1), row(W2)], WINDOW, T1)
    assert load_rows([], WINDOW, T2).rows_deleted == 2
    assert stored() == {}


def test_failure_rolls_back_the_whole_load(monkeypatch):
    load_rows([row(W1), row(W2)], WINDOW, T1)
    before = stored()

    def broken_upsert(dialect, rows):
        from sqlalchemy import text

        return text("INSERT INTO tabla_que_no_existe VALUES (1)")

    monkeypatch.setattr(load, "_upsert_statement", broken_upsert)
    with pytest.raises(ReportingStorageError):
        load_rows([row(W2, outbound=99)], WINDOW, T2)  # el borrado de W1 ya se había ejecutado
    assert stored() == before
