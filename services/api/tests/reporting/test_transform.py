"""transform: huella de los datos, versión del código y controles de coherencia (`data/process/weekly_performance/`).

Ejecutar desde services/api: uv run pytest tests/reporting/test_transform.py
"""

import re
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.reporting.tables import is_transient
from app.reporting.weeks import WeekWindow
from data.process.weekly_performance.transform import (
    CODE_VERSION,
    InconsistentResultError,
    check_consistency,
    fingerprint_events,
    transform_events,
)
from data.process.weekly_performance.validate import SourceSchemaError, validate_events
from tests.reporting.helpers import CURRENT, DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT, W1, W2, at, event, frame

WEEKS = WeekWindow(first=W1, last=W2).weeks


def row(**values):
    base = {
        "warehouse": "los_angeles",
        "client_id": "fashion-co",
        "week_start": W2,
        "inbound_units_count": 0,
        "outbound_orders_count": 0,
        "stockout_events_count": 0,
        "discrepancy_events_count": 0,
        "discrepancy_rate": 0.0,
    }
    return {**base, **values}


# --- Huella y versión ------------------------------------------------------------------------------------------------


def test_fingerprint_ignores_row_order_but_not_content():
    a = event(INBOUND, at(W2), quantity=5, order_id=1)
    b = event(OUTBOUND, at(W2), order_id=2)
    assert fingerprint_events(frame(a, b)) == fingerprint_events(frame(b, a))
    changed = {**b, "tags": {**b["tags"], "client_id": "otro-cliente"}}
    assert fingerprint_events(frame(a, changed)) != fingerprint_events(frame(a, b))
    assert fingerprint_events(frame(a)) != fingerprint_events(frame(a, b))
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint_events(frame()))


def test_code_version_is_a_short_hash():
    assert re.fullmatch(r"[0-9a-f]{16}", CODE_VERSION)


# --- Transformación completa -----------------------------------------------------------------------------------------


def test_transform_returns_rows_and_quality_counts():
    result = transform_events(
        frame(
            event(INBOUND, at(W2), quantity=40, order_id=1),
            *(event(OUTBOUND, at(W2), order_id=10 + n) for n in range(800)),
            event(DISCREPANCY, at(W2)),
            event(STOCKOUT, at(W2)),
            event(OUTBOUND, at(W2), warehouse="madrid", order_id=900),
        ),
        WEEKS,
    )
    (only,) = result.rows
    # 1/800 = 0.00125: numpy (round half to even) y Python pueden desempatar distinto; el control lo acepta.
    assert (only["inbound_units_count"], only["outbound_orders_count"], only["discrepancy_rate"]) == (40, 800, 0.0012)
    assert result.total_read == 804 and result.total_rejected == 1
    assert result.rejected == {OUTBOUND: {"invalid_warehouse": 1}}


def test_events_of_the_current_week_never_reach_the_report():
    result = transform_events(frame(event(INBOUND, at(CURRENT), quantity=9, order_id=1)), WEEKS)
    assert result.rows == []  # ventana incompleta: se descarta, no se mezcla con las semanas pedidas


# --- Controles de coherencia -----------------------------------------------------------------------------------------


def valid_of(*events):
    return validate_events(frame(*events)).valid


def test_consistent_rows_pass():
    check_consistency([row(outbound_orders_count=1)], valid_of(event(OUTBOUND, at(W2), order_id=1)), WEEKS)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row(outbound_orders_count=1), row(outbound_orders_count=0)], "repetidas"),
        ([row(outbound_orders_count=1, week_start=CURRENT)], "fuera de la ventana"),
        ([row(outbound_orders_count=1, warehouse="madrid")], "almacén no válido"),
        ([row(outbound_orders_count=1, stockout_events_count=-1)], "entero ≥ 0"),
        ([row(outbound_orders_count=1, discrepancy_rate=0.5)], "discrepancy_rate"),
        ([row(outbound_orders_count=2)], "total de outbound_orders_count"),
    ],
)
def test_inconsistent_rows_are_detected(rows, message):
    with pytest.raises(InconsistentResultError) as error:
        check_consistency(rows, valid_of(event(OUTBOUND, at(W2), order_id=1)), WEEKS)
    assert any(message in problem for problem in error.value.problems)


def test_rate_with_zero_orders_must_be_zero():
    with pytest.raises(InconsistentResultError):
        check_consistency(
            [row(discrepancy_events_count=1, discrepancy_rate=1.0)], valid_of(event(DISCREPANCY, at(W2))), WEEKS
        )
    check_consistency([row(discrepancy_events_count=1)], valid_of(event(DISCREPANCY, at(W2))), WEEKS)


# --- Esquema de la extracción ----------------------------------------------------------------------------------------


def test_missing_columns_fail_instead_of_rejecting_every_row():
    with pytest.raises(SourceSchemaError, match="tags"):
        validate_events(frame(event(INBOUND, at(W2), order_id=1)).drop(columns=["tags"]))


def test_unexpected_event_types_fail():
    with pytest.raises(SourceSchemaError, match="login_failed"):
        validate_events(frame(event("login_failed", at(W2))))


# --- Fallos transitorios y permanentes de la base --------------------------------------------------------------------


class _PgError(Exception):
    def __init__(self, message: str, sqlstate: str | None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (OperationalError("SELECT 1", {}, _PgError("conexión perdida", "08006")), True),
        (OperationalError("SELECT 1", {}, _PgError("el servidor se está apagando", "57P01")), True),
        (OperationalError("SELECT 1", {}, _PgError("demasiadas conexiones", "53300")), True),
        (OperationalError("SELECT 1", {}, _PgError("interbloqueo", "40P01")), True),
        (OperationalError("SELECT 1", {}, _PgError("connection timeout expired", None)), True),
        (OperationalError("SELECT 1", {}, _PgError("password authentication failed", None)), False),
        (ProgrammingError("SELECT 1", {}, _PgError("no existe la relación", "42P01")), False),
        (IntegrityError("INSERT", {}, _PgError("clave duplicada", "23505")), False),
        (OperationalError("SELECT 1", {}, sqlite3.OperationalError("database is locked")), True),
        (OperationalError("SELECT 1", {}, sqlite3.OperationalError("no such table: telemetry_events")), False),
        (PoolTimeoutError("QueuePool limit reached"), True),
    ],
)
def test_storage_errors_are_classified_as_transient_or_permanent(error, transient):
    assert is_transient(error) is transient
