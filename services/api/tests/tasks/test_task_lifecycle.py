"""Ciclo de vida de una tarea con `DeadLetterTask`: reintentos, fallos definitivos, DLQ y logs estructurados.

Celery ejecuta las tareas en el mismo proceso (modo eager de tests/conftest.py): los reintentos se encadenan sin esperar
el backoff, pero pasan por el mismo código (`retry_or_fail`, `on_failure`, señales). Las esperas reales de 2, 4 y 8 s
se comprueban con Redis y un worker reales (tests/tasks/test_e2e_docker.py y docs/async-tasks.md §9).
"""

import json
import pickle
import logging

import pytest
from celery import signals
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded
from sqlalchemy.exc import OperationalError

from app.tasks import dead_letters
from app.tasks.base import TransientTaskError
from app.tasks.diagnostics import ping
from tests.tasks.helpers import buggy, flaky


def events(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "trackflow.tasks"]


def test_transient_errors_are_retried_and_the_task_succeeds(caplog):
    caplog.set_level(logging.INFO, logger="trackflow.tasks")
    result = flaky.apply_async(kwargs={"failures": 2})
    assert result.state == "SUCCESS" and result.get() == {"attempt": 3}
    assert dead_letters.get(result.id) is None  # un éxito tras reintentos no va a la DLQ

    log = [(e["event"], e.get("attempt"), e.get("state"), e.get("countdown_s")) for e in events(caplog)]
    assert log == [
        ("task_started", 1, None, None),
        ("task_retry_scheduled", 1, None, 2),
        ("task_finished", 1, "RETRY", None),
        ("task_started", 2, None, None),
        ("task_retry_scheduled", 2, None, 4),
        ("task_finished", 2, "RETRY", None),
        ("task_started", 3, None, None),
        ("task_finished", 3, "SUCCESS", None),
    ]
    finished = [e for e in events(caplog) if e["event"] == "task_finished"]
    assert all(e["task_id"] == result.id and isinstance(e["duration_ms"], int) for e in finished)


def test_three_retries_at_most_then_dead_letter(caplog):
    """1 intento inicial + 3 reintentos (2, 4 y 8 s) = 4 ejecuciones; después, DLQ con `retries_exhausted`."""
    caplog.set_level(logging.INFO, logger="trackflow.tasks")
    result = flaky.apply_async(kwargs={"failures": 10})
    assert result.state == "FAILURE" and type(result.result).__name__ == "RetriesExhausted"
    countdowns = [e["countdown_s"] for e in events(caplog) if e["event"] == "task_retry_scheduled"]
    assert countdowns == [2, 4, 8]
    row = dead_letters.get(result.id)
    assert (row["reason"], row["attempts"], row["max_retries"]) == ("retries_exhausted", 4, 3)
    assert (row["exception_type"], row["task_name"]) == ("ConnectionError", "tests.flaky")
    assert row["error_message"] == "ConnectionError: base de datos no disponible"
    assert row["task_kwargs"] == {"failures": 10}  # los argumentos enviados (no los valores por defecto)
    # on_failure (DLQ) se ejecuta antes de la señal task_postrun.
    last = [e["event"] for e in events(caplog)][-3:]
    assert last == ["task_failed_permanently", "dead_letter_recorded", "task_finished"]


def test_permanent_errors_are_not_retried(caplog):
    caplog.set_level(logging.INFO, logger="trackflow.tasks")
    result = flaky.apply_async(kwargs={"failures": 10, "error": "permanent", "secret": "no-debe-guardarse"})
    assert result.state == "FAILURE" and type(result.result).__name__ == "PermanentTaskError"
    assert not [e for e in events(caplog) if e["event"] == "task_retry_scheduled"]
    row = dead_letters.get(result.id)
    assert (row["reason"], row["attempts"], row["exception_type"]) == ("permanent_error", 1, "ValueError")
    # Mensaje completo, pero sin credenciales; argumentos sensibles ocultos.
    assert "postgresql://***@db.example" in row["error_message"] and "clave" not in row["error_message"]
    assert row["task_kwargs"]["secret"] == "***"


def test_soft_time_limit_is_not_retried():
    result = flaky.apply_async(kwargs={"failures": 10, "error": "timeout"})
    assert type(result.result).__name__ == "TaskTimedOut"
    row = dead_letters.get(result.id)
    assert (row["reason"], row["attempts"], row["exception_type"]) == ("time_limit", 1, "SoftTimeLimitExceeded")


def test_an_unclassified_exception_is_a_permanent_failure():
    result = buggy.apply_async()
    assert result.state == "FAILURE"
    row = dead_letters.get(result.id)
    assert (row["reason"], row["attempts"], row["exception_type"]) == ("permanent_error", 1, "KeyError")


def test_hard_time_limit_is_recorded_without_the_attempt_number():
    """Con el timeout duro, Celery llama a on_failure desde el proceso padre del worker: no conoce el intento."""
    flaky.on_failure(TimeLimitExceeded(360), "hard-timeout-id", (), {"failures": 1}, None)
    row = dead_letters.get("hard-timeout-id")
    assert (row["reason"], row["attempts"], row["worker"]) == ("time_limit", None, None)
    assert row["exception_type"] == "TimeLimitExceeded"


def test_the_same_failure_reported_twice_is_stored_once(caplog):
    """Idempotencia: p. ej. el worker cae tras escribir en la DLQ y antes de confirmar el mensaje."""
    caplog.set_level(logging.INFO, logger="trackflow.tasks")
    error = TimeLimitExceeded(360)
    flaky.on_failure(error, "duplicado", (), {}, None)
    flaky.on_failure(error, "duplicado", (), {}, None)
    assert len([row for row in dead_letters.latest() if row["task_id"] == "duplicado"]) == 1
    assert [e["event"] for e in events(caplog)] == ["dead_letter_recorded", "dead_letter_duplicate"]


def test_expired_messages_go_to_the_dead_letter_queue():
    request = type("Request", (), {"id": "caducada", "retries": 0, "kwargs": {"failures": 0}, "hostname": "w@h"})()
    signals.task_revoked.send(sender=flaky, request=request, terminated=False, signum=None, expired=True)
    row = dead_letters.get("caducada")
    assert (row["reason"], row["attempts"], row["exception_type"]) == ("expired", 1, "TaskExpired")


def test_manual_revocations_are_not_failures():
    request = type("Request", (), {"id": "revocada", "retries": 0, "kwargs": {}, "hostname": "w@h"})()
    signals.task_revoked.send(sender=flaky, request=request, terminated=True, signum=15, expired=False)
    assert dead_letters.get("revocada") is None


def test_if_the_database_is_down_the_failure_is_kept_in_the_log(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="trackflow.tasks")
    attempts = []

    def database_down(row):
        attempts.append(row["task_id"])
        raise OperationalError("INSERT", {}, Exception("server closed the connection unexpectedly"))

    monkeypatch.setattr(dead_letters, "_insert", database_down)
    monkeypatch.setattr(dead_letters, "WRITE_RETRY_DELAYS", (0, 0))
    result = flaky.apply_async(kwargs={"failures": 10, "error": "permanent"})
    assert result.state == "FAILURE"
    assert len(attempts) == 3  # 1 + 2 reintentos de la escritura
    lost = next(e for e in events(caplog) if e["event"] == "dead_letter_not_persisted")
    assert (lost["task_id"], lost["reason"], lost["exception_type"]) == (result.id, "permanent_error", "ValueError")
    assert lost["storage_error"] == "Exception"
    assert next(r for r in caplog.records if "dead_letter_not_persisted" in r.getMessage()).levelno == logging.CRITICAL


def test_ping_proves_the_round_trip():
    result = ping.delay().get(timeout=5)
    assert result["pong"] is True and result["delay_seconds"] == 0 and isinstance(result["worker"], str)


@pytest.mark.parametrize("delay", [-1, 61, "5"])
def test_ping_rejects_invalid_delays_without_retrying(delay):
    result = ping.apply_async(kwargs={"delay_seconds": delay})
    assert type(result.result).__name__ == "PermanentTaskError"
    assert dead_letters.get(result.id)["exception_type"] == "ValueError"


def test_retries_carry_a_safe_exception_not_the_original(monkeypatch):
    """Regresión (worker real): el reintento viaja del proceso hijo al padre del worker. Con la excepción original de
    `data.pipelines`, el padre no podía importar su clase y se caía con ModuleNotFoundError."""
    captured = {}
    original = flaky.retry

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(flaky, "retry", spy)
    assert flaky.apply_async(kwargs={"failures": 1}).state == "SUCCESS"
    exc = captured["exc"]
    assert type(exc) is TransientTaskError and str(exc) == "ConnectionError"
    assert type(pickle.loads(pickle.dumps(exc))).__module__ == "app.tasks.base"
    assert captured["countdown"] == 2


@pytest.mark.parametrize(("simulate_hang", "outcome"), [(False, "TaskTimedOut"), (True, "SUCCESS")])
def test_ping_soft_time_limit(monkeypatch, simulate_hang, outcome):
    """El límite suave interrumpe la espera; con `simulate_hang` la tarea lo ignora (para probar el límite duro)."""
    calls = []

    def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 1:
            raise SoftTimeLimitExceeded()

    monkeypatch.setattr("app.tasks.diagnostics.time.sleep", sleep)
    result = ping.apply_async(kwargs={"delay_seconds": 0.05, "simulate_hang": simulate_hang})
    assert (type(result.result).__name__ if result.failed() else result.state) == outcome
