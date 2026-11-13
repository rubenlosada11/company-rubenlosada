"""observe: actividad cero, captura caída y mediciones perdidas o duplicadas (`data/pipelines/weekly_performance/`).

Ejecutar desde services/api: uv run pytest tests/reporting/test_observe.py
"""

import uuid
from datetime import timedelta

import pytest

from app.reporting.weeks import WeekWindow
from data.pipelines.weekly_performance import observe as observe_module
from data.pipelines.weekly_performance.extract import extract_events
from data.pipelines.weekly_performance.observe import capture_coverage, observe, source_health
from tests.reporting.helpers import INBOUND, OUTBOUND, W1, W2, at, event, insert, record_orders

WINDOW = WeekWindow(first=W2, last=W2)


def observed():
    return observe(WINDOW, "development", extract_events(WINDOW, "development"))


def test_source_health_counts_every_event_type_and_session_per_day():
    session = uuid.uuid4()
    login = event("login_succeeded", at(W2, 9))
    login["session_id"] = session
    navigation = event("navigation_section_viewed", at(W2, 10))
    navigation["session_id"] = session
    insert(login, navigation, event(OUTBOUND, at(W2 + timedelta(days=1)), order_id=1))
    health = source_health(WINDOW, "development")
    assert health["events_by_day"][W2.isoformat()] == 2
    assert health["sessions_by_day"][W2.isoformat()] == 1
    assert health["total_events"] == 3
    assert len(health["events_by_day"]) == 7
    assert W2.isoformat() not in health["silent_days"] and len(health["silent_days"]) == 5


def test_no_events_at_all_means_capture_is_probably_down():
    result = observed()
    assert "no_events_in_window" in result["warnings"]
    assert result["source_health"]["total_events"] == 0


def test_activity_without_orders_is_a_real_zero_not_a_silence():
    # La gente entra y navega (la captura funciona) pero no hay órdenes: el reporte vacío es real.
    insert(*(event("login_succeeded", at(W2 + timedelta(days=n))) for n in range(7)))
    result = observed()
    assert result["warnings"] == []
    assert result["capture_coverage"] == []


def test_capture_matches_the_inventory():
    record_orders(("inbound", "LA", at(W2, 9)), ("dispatch", "ZGZ", at(W2, 10)), ("loss", "ZGZ", at(W2, 11)))
    insert(
        event(INBOUND, at(W2, 9), order_id=1),
        event(OUTBOUND, at(W2, 10), warehouse="zaragoza", order_id=1),
        *(event("login_succeeded", at(W2 + timedelta(days=n))) for n in range(7)),
    )
    result = observed()
    assert result["capture_coverage"] == [
        {"week_start": W2.isoformat(), "warehouse": "los_angeles", "inbound_orders": 1, "inbound_events": 1,
         "outbound_orders": 0, "outbound_events": 0},
        {"week_start": W2.isoformat(), "warehouse": "zaragoza", "inbound_orders": 0, "inbound_events": 0,
         "outbound_orders": 1, "outbound_events": 1},
    ]  # fmt: skip
    assert result["warnings"] == []  # la pérdida (`loss`) no es un pedido despachado


def test_lost_measurements_are_flagged():
    record_orders(*(("dispatch", "LA", at(W2, 8 + n)) for n in range(3)))
    insert(event(OUTBOUND, at(W2, 8), order_id=1))  # 3 pedidos, 1 evento: se perdieron 2
    result = observed()
    assert "capture_gap" in result["warnings"]
    (row,) = result["capture_coverage"]
    assert (row["outbound_orders"], row["outbound_events"]) == (3, 1)


def test_duplicated_measurements_are_flagged():
    record_orders(("inbound", "LA", at(W2)))
    insert(event(INBOUND, at(W2), order_id=1), event(INBOUND, at(W2, 13), order_id=1))
    (row,) = observed()["capture_coverage"]
    assert (row["inbound_orders"], row["inbound_events"]) == (1, 2)


def test_coverage_ignores_orders_outside_the_window():
    record_orders(("dispatch", "LA", at(W1)))
    assert capture_coverage(WINDOW, extract_events(WINDOW, "development")) == []


def test_a_failing_signal_raises_so_the_flow_can_decide(monkeypatch):
    """observe no se traga el error: lo decide el flow (return_state=True), ver test_pipeline_prefect.py."""

    def broken(*args):
        raise ValueError("fallo de la señal")

    monkeypatch.setattr(observe_module, "source_health", broken)
    with pytest.raises(ValueError):
        observed()
