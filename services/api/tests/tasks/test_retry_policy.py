"""Configuración de Celery y política de reintentos (`app/celery_app.py`, `app/tasks/base.py`, DEV-55).

Ejecutar desde services/api: uv run pytest tests/tasks
"""

from datetime import timedelta

import pytest
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from app.celery_app import create_celery_app, describe_redis_url, get_redis_url
from app.reporting.tables import ReportingStorageError
from app.tasks.base import PERMANENT, TIMEOUT, TRANSIENT, backoff_countdown, classify, summary


def test_redis_url_is_the_single_source_for_broker_and_result_backend(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    app = create_celery_app()
    assert app.conf.broker_url == app.conf.result_backend == "redis://redis:6379/0" == get_redis_url()


def test_local_default_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert get_redis_url() == "redis://127.0.0.1:6379/0"
    monkeypatch.setenv("REDIS_URL", "   ")
    assert get_redis_url() == "redis://127.0.0.1:6379/0"


def test_redis_url_is_logged_without_credentials():
    assert describe_redis_url("redis://usuario:clave-secreta@redis:6380/2") == "redis://redis:6380/2"
    assert describe_redis_url("rediss://:clave@cache.example") == "rediss://cache.example:6379/0"


def test_reliability_settings(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    conf = create_celery_app().conf
    # Solo JSON: nunca pickle.
    assert (conf.task_serializer, conf.result_serializer) == ("json", "json")
    assert conf.accept_content == ["json"] and conf.result_accept_content == ["json"]
    # Estado STARTED, ACK al terminar, reentrega si el worker muere, sin prefetch de tareas largas.
    assert conf.task_track_started and conf.task_acks_late and conf.task_reject_on_worker_lost
    assert conf.task_acks_on_failure_or_timeout and conf.worker_prefetch_multiplier == 1
    # Timeouts: el suave antes que el duro; Redis no reentrega una tarea viva (visibility > límite duro).
    assert 0 < conf.task_soft_time_limit < conf.task_time_limit
    assert conf.broker_transport_options["visibility_timeout"] > conf.task_time_limit
    assert conf.result_expires == timedelta(days=1)
    # Flower ve las tareas encoladas y los eventos de los workers.
    assert conf.worker_send_task_events and conf.task_send_sent_event
    # Nada de ejecución síncrona en la configuración real (el modo eager solo existe en tests/conftest.py).
    assert not conf.task_always_eager


def test_backoff_is_exponential_and_never_immediate():
    assert [backoff_countdown(retries) for retries in range(3)] == [2, 4, 8]


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ReportingStorageError("OperationalError (SQLSTATE 08006)", transient=True), TRANSIENT),
        (ReportingStorageError("ProgrammingError (SQLSTATE 42P01)", transient=False), PERMANENT),
        (ConnectionRefusedError("conexión rechazada"), TRANSIENT),
        (TimeoutError("sin respuesta"), TRANSIENT),
        (ValueError("datos no válidos"), PERMANENT),
        (ZeroDivisionError(), PERMANENT),
        (SoftTimeLimitExceeded(), TIMEOUT),
        (TimeLimitExceeded(360), TIMEOUT),
    ],
)
def test_errors_are_classified(error, kind):
    assert classify(error) == kind


def chained(outer: Exception, cause: Exception) -> Exception:
    try:
        try:
            raise cause
        except Exception as inner:
            raise outer from inner
    except Exception as error:
        return error


def test_classification_follows_the_cause_chain():
    """El pipeline envuelve sus errores en `PipelineRunFailed`: lo que decide es la causa."""
    transient = chained(RuntimeError("ejecución fallida"), ReportingStorageError("x", transient=True))
    permanent = chained(RuntimeError("ejecución fallida"), ZeroDivisionError())
    timeout = chained(RuntimeError("ejecución fallida"), SoftTimeLimitExceeded())
    assert (classify(transient), classify(permanent), classify(timeout)) == (TRANSIENT, PERMANENT, TIMEOUT)


def test_summary_has_only_error_types():
    error = chained(RuntimeError("postgresql://usuario:clave@host/db"), ZeroDivisionError("detalle"))
    assert summary(error) == "RuntimeError ← ZeroDivisionError"
