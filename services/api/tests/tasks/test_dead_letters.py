"""DLQ persistente (`app/tasks/dead_letters.py`): idempotencia, censura de secretos, lectura y errores de la base.

Sobre SQLite temporal (tests/conftest.py). Contra PostgreSQL con la migración real: test_dead_letters_postgres.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.tasks import dead_letters


def record(task_id: str = "t-1", **overrides) -> bool:
    fields = {
        "task_id": task_id,
        "task_name": "reporting.run_weekly_performance",
        "reason": "retries_exhausted",
        "error": ConnectionError("base no disponible"),
        "attempts": 4,
        "max_retries": 3,
        "kwargs": {"week_start": "2026-11-09", "weeks": 2},
        "worker": "celery@worker-1",
    }
    return dead_letters.record(**{**fields, **overrides})


def test_record_and_read_back():
    assert record() is True
    row = dead_letters.get("t-1")
    assert row["reason"] == "retries_exhausted" and row["attempts"] == 4 and row["max_retries"] == 3
    assert row["exception_type"] == "ConnectionError" and row["error_message"] == "ConnectionError: base no disponible"
    assert row["task_kwargs"] == {"week_start": "2026-11-09", "weeks": 2} and row["worker"] == "celery@worker-1"
    assert row["failed_at"] is not None and row["created_at"] is not None


def test_recording_is_idempotent_by_task_id():
    assert record() is True
    assert record(reason="permanent_error", attempts=1) is False
    rows = [row for row in dead_letters.latest() if row["task_id"] == "t-1"]
    assert len(rows) == 1 and rows[0]["reason"] == "retries_exhausted"  # se conserva el primero


def test_latest_is_newest_first_and_limited():
    now = datetime.now(UTC)
    for n in range(3):
        record(f"t-{n}", failed_at=now - timedelta(minutes=n))
    assert [row["task_id"] for row in dead_letters.latest()] == ["t-0", "t-1", "t-2"]
    assert len(dead_letters.latest(limit=2)) == 2


def test_unknown_reason_is_rejected():
    with pytest.raises(ValueError):
        record(reason="otra cosa")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "could not connect to postgresql+psycopg://postgres.ref:MiClave@aws-0.pooler.supabase.com:5432/postgres",
            "could not connect to postgresql+psycopg://***@aws-0.pooler.supabase.com:5432/postgres",
        ),
        ("redis://:clave-redis@redis:6379/0 no responde", "redis://***@redis:6379/0 no responde"),
        ("password=hunter2 host=db", "password=*** host=db"),
        ("Authorization: Bearer abc.def", "Authorization: *** abc.def"),
        ("token=eyJhbGciOi; resto", "token=***; resto"),
        ("sin secretos", "sin secretos"),
    ],
)
def test_redact(text, expected):
    assert dead_letters.redact(text) == expected


def test_redact_truncates_long_messages():
    assert len(dead_letters.redact("x" * 10_000)) == dead_letters.MAX_ERROR_LENGTH


def test_safe_kwargs_keeps_only_useful_scalars():
    kwargs = {
        "week_start": "2026-11-09",
        "weeks": 2,
        "dry_run": False,
        "request_id": None,
        "user_email": "ana@trackflow.test",
        "api_token": "secreto",
        "rows": [1, 2, 3],
        "note": "x" * 500,
    }
    safe = dead_letters.safe_kwargs(kwargs)
    assert safe["week_start"] == "2026-11-09" and safe["weeks"] == 2 and safe["dry_run"] is False
    assert safe["request_id"] is None and safe["user_email"] == "***" and safe["api_token"] == "***"
    assert safe["rows"] == "<list>" and len(safe["note"]) == dead_letters.MAX_ARGUMENT_LENGTH


def test_describe_error_follows_the_cause_chain():
    try:
        try:
            raise ZeroDivisionError("division by zero")
        except ZeroDivisionError as cause:
            raise RuntimeError("PipelineRunFailed") from cause
    except RuntimeError as error:
        assert dead_letters.describe_error(error) == (
            "ZeroDivisionError",
            "RuntimeError: PipelineRunFailed ← ZeroDivisionError: division by zero",
        )


def test_transient_database_errors_are_retried(monkeypatch):
    calls = []
    original = dead_letters._insert

    def flaky_insert(row):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("INSERT", {}, Exception("server closed the connection unexpectedly"))
        return original(row)

    monkeypatch.setattr(dead_letters, "_insert", flaky_insert)
    monkeypatch.setattr(dead_letters, "WRITE_RETRY_DELAYS", (0, 0))
    assert record() is True and len(calls) == 2


def test_permanent_database_errors_are_not_retried(monkeypatch):
    calls = []

    def missing_table(row):
        calls.append(1)
        raise ProgrammingError("INSERT", {}, Exception('relation "task_dead_letters" does not exist'))

    monkeypatch.setattr(dead_letters, "_insert", missing_table)
    with pytest.raises(dead_letters.DeadLetterStorageError) as error:
        record()
    assert len(calls) == 1 and str(error.value) == "Exception"


def test_describe_error_respects_raise_from_none():
    """`raise … from None` oculta la excepción del driver (puede llevar la cadena de conexión): no se guarda."""
    try:
        try:
            raise RuntimeError("could not connect to postgresql://usuario:clave@host/db")
        except RuntimeError:
            raise ConnectionError("OperationalError (SQLSTATE 08006)") from None
    except ConnectionError as error:
        assert dead_letters.describe_error(error) == (
            "ConnectionError",
            "ConnectionError: OperationalError (SQLSTATE 08006)",
        )
