"""extract: filtros en SQL y solo lectura (`data/pipelines/weekly_performance/extract.py`, PIPELINE_DESIGN.md §6.1).

Ejecutar desde services/api: uv run pytest tests/reporting/test_extract.py
"""

from datetime import timedelta

import pytest
from sqlalchemy.exc import OperationalError

from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import WeekWindow
from data.pipelines.weekly_performance import extract
from data.pipelines.weekly_performance.extract import extract_events
from data.process.weekly_performance.events import COLUMNS, SOURCE_EVENT_TYPES
from tests.reporting.helpers import CURRENT, INBOUND, OUTBOUND, W0, W1, W2, at, event, insert, telemetry_count

WINDOW = WeekWindow(first=W1, last=W2)


def test_reads_only_the_four_event_types():
    rows = [event(event_type, at(W2), order_id=n + 1) for n, event_type in enumerate(SOURCE_EVENT_TYPES)]
    insert(*rows, event("login_failed", at(W2)), event("direct_stock_edit_rejected", at(W2)))
    df = extract_events(WINDOW, "development")
    assert sorted(df["event_type"]) == sorted(SOURCE_EVENT_TYPES)
    assert list(df.columns) == COLUMNS


def test_window_is_start_inclusive_end_exclusive():
    inside_first = event(OUTBOUND, at(W1, 0, 0, 0), order_id=1)
    inside_last = event(OUTBOUND, at(CURRENT - timedelta(days=1), 23, 59, 59), order_id=2)
    before = event(OUTBOUND, at(W1 - timedelta(days=1), 23, 59, 59), order_id=3)
    after = event(OUTBOUND, at(CURRENT, 0, 0, 0), order_id=4)
    insert(inside_first, inside_last, before, after)
    df = extract_events(WINDOW, "development")
    assert set(df["id"]) == {inside_first["id"], inside_last["id"]}


def test_reads_only_the_pipeline_environment():
    insert(
        event(INBOUND, at(W2), environment="development", order_id=1),
        event(INBOUND, at(W2), environment="production", order_id=2),
        event(INBOUND, at(W2), environment="test", order_id=3),
    )
    assert extract_events(WINDOW, "production")["tags"].map(lambda tags: tags["order_id"]).tolist() == [2]


def test_rows_come_in_chronological_order_with_their_tags():
    late = event(OUTBOUND, at(W2, 18), order_id=2)
    early = event(OUTBOUND, at(W2, 9), order_id=1)
    insert(late, early)
    df = extract_events(WINDOW, "development")
    assert df["id"].tolist() == [early["id"], late["id"]]
    assert df.loc[0, "tags"]["client_id"] == "fashion-co"


def test_empty_result_keeps_the_columns():
    insert(event(OUTBOUND, at(W0), order_id=1))
    df = extract_events(WINDOW, "development")
    assert df.empty and list(df.columns) == COLUMNS


def test_never_writes_to_telemetry_events():
    insert(event(OUTBOUND, at(W2), order_id=1))
    before = telemetry_count()
    extract_events(WINDOW, "development")
    assert telemetry_count() == before


def test_database_failure_is_a_storage_error_without_details(monkeypatch):
    def broken_engine():
        raise OperationalError("SELECT …", {}, Exception("postgresql://usuario:secreto@host/db"))

    monkeypatch.setattr(extract, "telemetry_engine", broken_engine)
    with pytest.raises(ReportingStorageError) as error:
        extract_events(WINDOW, "development")
    assert "secreto" not in str(error.value)
