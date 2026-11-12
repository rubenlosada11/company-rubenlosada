"""Análisis técnico de la telemetría (`app/telemetry/analysis.py`): SQL + Pandas, sin Supabase.

- Las consultas (filtros de periodo y de `event_type` en SQL) se prueban contra la SQLite temporal de cada test.
- La lógica de Pandas se prueba también con DataFrames construidos a mano (`load_events` sustituido): formatos de
  timestamp, `tags` ausentes o mal formados, valores nulos y divisiones entre cero.

Ejecutar desde services/api: uv run pytest tests/test_telemetry_analysis.py
"""

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.telemetry import analysis, storage
from app.telemetry.analysis import ERROR_EVENT_TYPES, TelemetryAnalysisError

DAY1 = datetime(2026, 11, 10, tzinfo=UTC)
DAY2 = DAY1 + timedelta(days=1)
DAY3 = DAY1 + timedelta(days=2)
METRICS = [
    analysis.events_per_day,
    analysis.error_rate_by_type,
    analysis.errors_per_day,
    analysis.auth_failure_rate,
    analysis.submission_failures_by_form,
]


def store(*events: tuple[str, datetime, dict]) -> None:
    """Guarda filas en `telemetry_events` (sin pasar por el contrato: aquí se prueba el análisis, no la captura)."""
    rows = [
        {
            "id": uuid.uuid4(),
            "event_type": event_type,
            "timestamp": timestamp,
            "service": "frontend",
            "tags": tags,
            "session_id": None,
            "user_id": None,
            "request_id": None,
            "schema_version": "1.0.0",
            "environment": "test",
        }
        for event_type, timestamp, tags in events
    ]
    with storage.telemetry_engine().begin() as connection:
        connection.execute(storage.telemetry_events.insert(), rows)


@pytest.fixture
def frame(monkeypatch):
    """Sustituye la carga SQL por un DataFrame dado: `frame({"timestamp": [...], ...})`."""

    def _use(columns: dict) -> None:
        def fake_load(start, end, wanted, event_types=None, *, metric):
            df = pd.DataFrame(columns)
            if event_types is not None and "event_type" in df:
                df = df[df["event_type"].isin(list(event_types))]
            return df[list(wanted)].reset_index(drop=True)

        monkeypatch.setattr(analysis, "load_events", fake_load)

    return _use


@pytest.fixture
def sql_log():
    """Sentencias SQL que llegan a la base durante el test."""
    statements: list[str] = []
    engine = storage.telemetry_engine()

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    yield statements
    event.remove(engine, "before_cursor_execute", capture)


# --- Volumen diario ------------------------------------------------------------------------------------------------


def test_events_per_day_counts_every_event_type_per_utc_day_in_order():
    store(
        ("navigation_section_viewed", DAY2 + timedelta(hours=5), {"section": "dashboard"}),
        ("login_failed", DAY1 + timedelta(hours=1), {"failure_reason": "invalid_credentials"}),
        ("inbound_order_created", DAY1 + timedelta(hours=2), {"warehouse": "zaragoza"}),
    )
    assert analysis.events_per_day(DAY1, DAY3) == [
        {"date": "2026-11-10", "total_events": 2},
        {"date": "2026-11-11", "total_events": 1},
    ]


def test_events_per_day_fills_days_without_events_with_zero():
    store(("form_started", DAY1 + timedelta(hours=3), {"form_id": "login"}))
    assert analysis.events_per_day(DAY1, DAY1 + timedelta(days=3)) == [
        {"date": "2026-11-10", "total_events": 1},
        {"date": "2026-11-11", "total_events": 0},
        {"date": "2026-11-12", "total_events": 0},
    ]


def test_period_start_is_inclusive_and_end_is_exclusive():
    store(
        ("form_started", DAY1 - timedelta(microseconds=1), {}),
        ("form_started", DAY1, {}),
        ("form_started", DAY2 - timedelta(microseconds=1), {}),
        ("form_started", DAY2, {}),
    )
    assert analysis.events_per_day(DAY1, DAY2) == [{"date": "2026-11-10", "total_events": 2}]


def test_days_are_utc_days_whatever_the_offset_of_the_period():
    # 23:30 en Madrid (+01:00) el día 10 son las 22:30 UTC del día 10; 01:30 de Madrid el 11 son las 00:30 UTC del 11.
    madrid = timezone(timedelta(hours=1))
    store(
        ("form_started", datetime(2026, 11, 10, 23, 30, tzinfo=madrid), {}),
        ("form_started", datetime(2026, 11, 11, 1, 30, tzinfo=madrid), {}),
    )
    start = datetime(2026, 11, 10, 1, 0, tzinfo=madrid)  # 00:00 UTC del día 10
    end = datetime(2026, 11, 12, 1, 0, tzinfo=madrid)  # 00:00 UTC del día 12
    assert analysis.events_per_day(start, end) == [
        {"date": "2026-11-10", "total_events": 1},
        {"date": "2026-11-11", "total_events": 1},
    ]


def test_naive_dates_are_read_as_utc():
    store(("form_started", DAY1 + timedelta(hours=1), {}))
    naive = analysis.events_per_day(DAY1.replace(tzinfo=None), DAY2.replace(tzinfo=None))
    assert naive == analysis.events_per_day(DAY1, DAY2) == [{"date": "2026-11-10", "total_events": 1}]


# --- Incidencias por tipo y por día --------------------------------------------------------------------------------


def errors_fixture() -> None:
    store(
        ("login_failed", DAY1 + timedelta(hours=1), {"failure_reason": "invalid_credentials"}),
        ("login_failed", DAY1 + timedelta(hours=2), {"failure_reason": "invalid_credentials"}),
        ("login_failed", DAY2 + timedelta(hours=1), {"failure_reason": "account_inactive"}),
        ("form_validation_failed", DAY2 + timedelta(hours=2), {"form_id": "login", "failed_fields": ["email"]}),
        ("backend_request_failed", DAY2 + timedelta(hours=3), {"failure_kind": "timeout", "api_route": "/inventory"}),
        # No son incidencias técnicas: rechazos de negocio y la respuesta vista por el formulario (ya contada).
        ("direct_stock_edit_rejected", DAY1 + timedelta(hours=3), {"warehouse": "zaragoza"}),
        ("inventory_order_rejected", DAY1 + timedelta(hours=3), {"rejection_reason": "insufficient_stock"}),
        ("form_submitted", DAY1 + timedelta(hours=1), {"form_id": "login", "outcome": "unauthorized"}),
        ("navigation_section_viewed", DAY1 + timedelta(hours=4), {"section": "dashboard"}),
    )


def test_error_rate_by_type_groups_by_category_event_type_and_catalog_reason():
    errors_fixture()
    assert analysis.error_rate_by_type(DAY1, DAY3) == [
        {
            "error_category": "authentication",
            "event_type": "login_failed",
            "reason": "invalid_credentials",
            "errors": 2,
            "share_pct": 40.0,
        },
        {
            "error_category": "api_communication",
            "event_type": "backend_request_failed",
            "reason": "timeout",
            "errors": 1,
            "share_pct": 20.0,
        },
        {
            "error_category": "authentication",
            "event_type": "login_failed",
            "reason": "account_inactive",
            "errors": 1,
            "share_pct": 20.0,
        },
        {
            "error_category": "validation",
            "event_type": "form_validation_failed",
            "reason": None,
            "errors": 1,
            "share_pct": 20.0,
        },
    ]


def test_errors_per_day_uses_the_same_classification_as_error_rate_by_type():
    errors_fixture()
    daily = analysis.errors_per_day(DAY1, DAY3)
    assert daily == [{"date": "2026-11-10", "errors": 2}, {"date": "2026-11-11", "errors": 3}]
    assert sum(row["errors"] for row in daily) == sum(row["errors"] for row in analysis.error_rate_by_type(DAY1, DAY3))


def test_error_metrics_filter_event_types_and_period_in_sql(sql_log):
    analysis.error_rate_by_type(DAY1, DAY2)
    analysis.errors_per_day(DAY1, DAY2)
    selects = [statement for statement in sql_log if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2
    for statement in selects:
        assert "telemetry_events.timestamp >=" in statement and "telemetry_events.timestamp <" in statement
        assert "telemetry_events.event_type IN" in statement


def test_events_per_day_reads_only_the_timestamp_column_of_the_period(sql_log):
    analysis.events_per_day(DAY1, DAY2)
    (statement,) = [s for s in sql_log if s.lstrip().upper().startswith("SELECT")]
    selected = statement.split("FROM")[0]
    assert "timestamp" in selected and "tags" not in selected and "event_type" not in selected
    assert "WHERE" in statement and "event_type IN" not in statement


def test_every_classified_error_type_is_in_the_catalog():
    from app.telemetry import contract

    for event_type, (_category, reason_key) in ERROR_EVENT_TYPES.items():
        allowed = contract.allowed_properties(event_type)
        assert allowed, event_type
        assert reason_key is None or reason_key in allowed, (event_type, reason_key)


def test_missing_or_malformed_reasons_become_null(frame):
    frame(
        {
            "timestamp": [DAY1] * 4,
            "event_type": ["login_failed"] * 4,
            "tags": [{}, {"failure_reason": None}, {"failure_reason": ["lista"]}, "no es un objeto"],
        }
    )
    assert analysis.error_rate_by_type(DAY1, DAY2) == [
        {
            "error_category": "authentication",
            "event_type": "login_failed",
            "reason": None,
            "errors": 4,
            "share_pct": 100.0,
        }
    ]


# --- Autenticación -------------------------------------------------------------------------------------------------


def test_auth_failure_rate_is_failed_over_failed_plus_succeeded_per_day():
    store(
        ("login_failed", DAY1 + timedelta(hours=1), {"failure_reason": "invalid_credentials"}),
        ("login_succeeded", DAY1 + timedelta(hours=1, minutes=1), {"user_role": "user"}),
        ("login_succeeded", DAY1 + timedelta(hours=2), {"user_role": "admin"}),
        ("login_failed", DAY1 + timedelta(hours=3), {"failure_reason": "invalid_credentials"}),
        ("login_failed", DAY2 + timedelta(hours=1), {"failure_reason": "account_inactive"}),
        ("session_ended", DAY1 + timedelta(hours=4), {"end_reason": "user_logout"}),
    )
    assert analysis.auth_failure_rate(DAY1, DAY3) == [
        {"date": "2026-11-10", "failed": 2, "succeeded": 2, "attempts": 4, "failure_rate_pct": 50.0},
        {"date": "2026-11-11", "failed": 1, "succeeded": 0, "attempts": 1, "failure_rate_pct": 100.0},
    ]


def test_auth_failure_rate_loads_both_login_events_in_one_query(sql_log):
    analysis.auth_failure_rate(DAY1, DAY2)
    (statement,) = [s for s in sql_log if s.lstrip().upper().startswith("SELECT")]
    assert "event_type IN" in statement


def test_auth_failure_rate_with_only_successes_is_zero_and_without_attempts_is_empty():
    assert analysis.auth_failure_rate(DAY1, DAY2) == []
    store(("login_succeeded", DAY1 + timedelta(hours=1), {"user_role": "user"}))
    assert analysis.auth_failure_rate(DAY1, DAY2) == [
        {"date": "2026-11-10", "failed": 0, "succeeded": 1, "attempts": 1, "failure_rate_pct": 0.0}
    ]


def test_percentage_never_divides_by_zero():
    result = analysis.percentage(pd.Series([0, 3]), pd.Series([0, 4]))
    assert pd.isna(result[0]) and result[1] == 75.0
    assert analysis.records(pd.DataFrame({"rate": result})) == [{"rate": None}, {"rate": 75.0}]


# --- Envíos fallidos por formulario --------------------------------------------------------------------------------


def test_submission_failures_by_form_counts_non_success_outcomes():
    store(
        (
            "form_submitted",
            DAY1 + timedelta(hours=1),
            {"form_id": "login", "outcome": "unauthorized", "http_status": 401},
        ),
        ("form_submitted", DAY1 + timedelta(hours=1), {"form_id": "login", "outcome": "success", "http_status": 200}),
        ("form_submitted", DAY1 + timedelta(hours=2), {"form_id": "inventory_inbound", "outcome": "success"}),
        ("form_submitted", DAY1 + timedelta(hours=2), {"form_id": "inventory_inbound", "outcome": "server_error"}),
        ("form_submitted", DAY1 + timedelta(hours=2), {"form_id": "inventory_inbound", "outcome": "network_error"}),
        ("form_submitted", DAY1 + timedelta(hours=3), {"form_id": "inventory_outbound", "outcome": "success"}),
    )
    assert analysis.submission_failures_by_form(DAY1, DAY2) == [
        {"form_id": "inventory_inbound", "submissions": 3, "failed": 2, "failure_rate_pct": 66.67},
        {"form_id": "login", "submissions": 2, "failed": 1, "failure_rate_pct": 50.0},
        {"form_id": "inventory_outbound", "submissions": 1, "failed": 0, "failure_rate_pct": 0.0},
    ]


def test_submissions_without_outcome_or_form_id_are_counted_safely(frame):
    frame(
        {
            "timestamp": [DAY1] * 3,
            "event_type": ["form_submitted"] * 3,
            "tags": [{"form_id": "login"}, {"outcome": "server_error"}, None],
        }
    )
    assert analysis.submission_failures_by_form(DAY1, DAY2) == [
        {"form_id": None, "submissions": 2, "failed": 1, "failure_rate_pct": 50.0},
        {"form_id": "login", "submissions": 1, "failed": 0, "failure_rate_pct": 0.0},
    ]


# --- Datos vacíos, nulos y formatos --------------------------------------------------------------------------------


def test_empty_period_gives_zero_days_and_empty_lists():
    assert analysis.events_per_day(DAY1, DAY3) == [
        {"date": "2026-11-10", "total_events": 0},
        {"date": "2026-11-11", "total_events": 0},
    ]
    assert analysis.errors_per_day(DAY1, DAY2) == [{"date": "2026-11-10", "errors": 0}]
    assert analysis.error_rate_by_type(DAY1, DAY2) == []
    assert analysis.auth_failure_rate(DAY1, DAY2) == []
    assert analysis.submission_failures_by_form(DAY1, DAY2) == []


def test_timestamps_in_different_formats_are_converted_to_utc_before_grouping(frame):
    frame(
        {
            "timestamp": [
                "2026-11-10T23:30:00Z",
                "2026-11-11T00:30:00+02:00",  # 22:30 UTC del día 10
                "2026-11-11T01:00:00",  # sin zona: UTC
                datetime(2026, 11, 11, 2, 0, tzinfo=UTC),
                datetime(2026, 11, 11, 3, 0),  # datetime sin zona (lo que devuelve SQLite): UTC
                pd.Timestamp("2026-11-11T04:00:00-05:00"),  # 09:00 UTC del día 11
            ]
        }
    )
    assert analysis.events_per_day(DAY1, DAY3) == [
        {"date": "2026-11-10", "total_events": 2},
        {"date": "2026-11-11", "total_events": 4},
    ]


def test_null_or_malformed_timestamps_are_discarded(frame, caplog):
    frame({"timestamp": ["2026-11-10T10:00:00Z", None, "no es una fecha", "2026-13-45T99:00:00Z"]})
    assert analysis.events_per_day(DAY1, DAY2) == [{"date": "2026-11-10", "total_events": 1}]
    assert "3 eventos con timestamp no válido" in caplog.text


def test_results_are_json_serializable_and_deterministic():
    errors_fixture()
    store(("login_succeeded", DAY1 + timedelta(hours=5), {"user_role": "user"}))
    for metric in METRICS:
        first = metric(DAY1, DAY3)
        json.dumps(first, allow_nan=False)  # sin NaN, datetime ni tipos de numpy
        assert metric(DAY1, DAY3) == first
        assert all(type(value) in (str, int, float, type(None)) for row in first for value in row.values())


@pytest.mark.parametrize("metric", METRICS)
def test_every_metric_rejects_an_empty_or_inverted_period(metric):
    with pytest.raises(ValueError):
        metric(DAY2, DAY1)
    with pytest.raises(ValueError):
        metric(DAY1, DAY1)


@pytest.mark.parametrize("metric", METRICS)
def test_a_database_failure_is_a_telemetry_analysis_error(metric, monkeypatch):
    def broken():
        raise OperationalError("SELECT", {}, Exception("conexión rechazada"))

    monkeypatch.setattr(analysis, "telemetry_engine", broken)
    with pytest.raises(TelemetryAnalysisError) as error:
        metric(DAY1, DAY2)
    assert "conexión" not in str(error.value)
