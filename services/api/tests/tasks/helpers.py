"""Tareas de prueba de `DeadLetterTask` (se importan siempre desde aquí: un solo registro en Celery)."""

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import DeadLetterTask


@celery_app.task(bind=True, base=DeadLetterTask, name="tests.flaky")
def flaky(self, failures: int, error: str = "transient", secret: str | None = None):
    """Falla en los `failures` primeros intentos (según `self.request.retries`) y después termina bien."""
    if self.request.retries < failures:
        exc = {
            "transient": ConnectionError("base de datos no disponible"),
            "permanent": ValueError("dato no válido en postgresql://usuario:clave@db.example/postgres"),
            "timeout": SoftTimeLimitExceeded(),
        }[error]
        self.retry_or_fail(exc)
    return {"attempt": self.request.retries + 1}


@celery_app.task(bind=True, base=DeadLetterTask, name="tests.buggy")
def buggy(self):
    """Una excepción que la tarea no clasifica (un bug): Celery la marca FAILURE sin pasar por retry_or_fail."""
    return {}["no-existe"]
