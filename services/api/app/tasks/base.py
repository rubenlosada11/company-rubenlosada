"""Clase base de las tareas de TrackFlow: reintentos con backoff exponencial y Dead Letter Queue.

Política de reintentos (docs/async-tasks.md §5):

- **1 intento inicial + `MAX_RETRIES` (3) reintentos = 4 ejecuciones como máximo.** `self.request.retries` cuenta los
  reintentos ya hechos (0 en el intento inicial), así que el intento en curso es `retries + 1`.
- **Backoff exponencial**, nunca inmediato: el reintento n espera `2 × 2^(n-1)` s → 2, 4 y 8 s (`backoff_countdown`).
  El reintento es un mensaje nuevo con el mismo `task_id` y una cuenta atrás (`countdown`), así que el worker queda
  libre mientras espera.
- **Solo se reintentan los errores transitorios** (`classify`): base de datos caída o saturada
  (`ReportingStorageError.transient`), conexión de red cortada, o un recurso ocupado que la tarea marca como transitorio
  (el pipeline ya en curso). Un error permanente (datos no válidos, tabla inexistente, un bug) falla a la primera:
  reintentarlo solo retrasaría el mismo error. Un límite de tiempo superado tampoco se reintenta.

Cuando la tarea falla definitivamente, lanza una `TaskFailure` con un mensaje seguro (solo tipos de error) cuya causa
(`__cause__`) es el error original, y Celery llama a `on_failure` → `dead_letters.record_failure`. `on_failure` no se
llama en un reintento (eso es `RETRY`, no `FAILURE`), así que cada tarea llega a la DLQ como mucho una vez por
ejecución completa; si aun así llegara dos veces, la tabla lo ignora (`task_id` único).
"""

import logging
from typing import Any, NoReturn

from celery import Task, signals
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from app.tasks import dead_letters
from app.tasks.observability import attempt_of, log_event

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2

TRANSIENT = "transient"
PERMANENT = "permanent"
TIMEOUT = "timeout"


class TransientTaskError(Exception):
    """Fallo transitorio que se va a reintentar. Es la excepción que viaja con el reintento (`self.retry(exc=…)`).

    Nunca se reintenta con la excepción original: el proceso hijo del worker se la envía al padre (y al result backend)
    y el padre tendría que poder importar su clase. Una excepción de `data.pipelines` (que solo importa el hijo, de
    forma perezosa) tumbaba el proceso principal con `ModuleNotFoundError` (comprobado con el worker real en Docker).
    """


class TaskFailure(Exception):
    """Fallo definitivo de una tarea. Su mensaje solo lleva tipos de error; el error original va en `__cause__`."""

    reason = dead_letters.PERMANENT_ERROR


class RetriesExhausted(TaskFailure):
    """Error transitorio que siguió fallando en el intento inicial y en los `MAX_RETRIES` reintentos."""

    reason = dead_letters.RETRIES_EXHAUSTED


class PermanentTaskError(TaskFailure):
    """Error no recuperable: no se ha reintentado."""

    reason = dead_letters.PERMANENT_ERROR


class TaskTimedOut(TaskFailure):
    """La tarea superó su límite de tiempo suave (`SoftTimeLimitExceeded`)."""

    reason = dead_letters.TIME_LIMIT


class TaskExpired(TaskFailure):
    """El mensaje caducó en la cola antes de que un worker lo empezara."""

    reason = dead_letters.EXPIRED


def backoff_countdown(retries: int) -> int:
    """Segundos de espera antes del reintento `retries + 1`: 2, 4, 8… (`retries` = reintentos ya hechos)."""
    return BACKOFF_BASE_SECONDS * 2**retries


def classify(error: BaseException) -> str:
    """`TRANSIENT`, `PERMANENT` o `TIMEOUT`, mirando toda la cadena de causas (el pipeline envuelve sus errores)."""
    chain = dead_letters.error_chain(error)
    if any(isinstance(item, (SoftTimeLimitExceeded, TimeLimitExceeded)) for item in chain):
        return TIMEOUT
    for item in chain:
        # `ReportingStorageError.transient`: conexión cortada, base reiniciando, demasiadas conexiones, bloqueo…
        if getattr(item, "transient", None) is True:
            return TRANSIENT
        if isinstance(item, (ConnectionError, TimeoutError)):
            return TRANSIENT
    return PERMANENT


def summary(error: BaseException) -> str:
    """Tipos de error de la cadena (`PipelineRunFailed ← ZeroDivisionError`): nunca mensajes ni datos."""
    return " ← ".join(type(item).__name__ for item in dead_letters.error_chain(error))


class DeadLetterTask(Task):
    """Tarea con reintentos clasificados y registro en la DLQ cuando falla definitivamente."""

    max_retries = MAX_RETRIES
    # Marca para los ganchos globales (p. ej. `task_revoked`): esta tarea usa la DLQ.
    uses_dead_letters = True

    def retry_or_fail(self, error: BaseException, *, transient: bool | None = None) -> NoReturn:
        """Programa un reintento con backoff si `error` es transitorio y quedan reintentos; si no, falla del todo.

        `transient` fuerza la clasificación cuando la tarea sabe más que `classify` (p. ej. «pipeline ya en curso»).
        """
        kind = classify(error)
        if transient is not None and kind != TIMEOUT:
            kind = TRANSIENT if transient else PERMANENT
        retries = self.request.retries
        attempt = retries + 1
        common = {"task_id": self.request.id, "task_name": self.name, "attempt": attempt, "error": summary(error)}
        if kind == TRANSIENT and retries < self.max_retries:
            countdown = backoff_countdown(retries)
            log_event(
                "task_retry_scheduled",
                logging.WARNING,
                **common,
                next_attempt=attempt + 1,
                retries_left=self.max_retries - retries - 1,
                countdown_s=countdown,
            )
            raise self.retry(exc=TransientTaskError(summary(error)), countdown=countdown) from error
        if kind == TRANSIENT:
            failure: TaskFailure = RetriesExhausted(
                f"{summary(error)} tras {attempt} intentos (1 inicial + {self.max_retries} reintentos)"
            )
        elif kind == TIMEOUT:
            failure = TaskTimedOut(f"{summary(error)} en el intento {attempt}")
        else:
            failure = PermanentTaskError(f"{summary(error)} en el intento {attempt} (no se reintenta)")
        log_event("task_failed_permanently", logging.ERROR, **common, reason=failure.reason)
        raise failure from error

    def on_failure(self, exc: BaseException, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Fallo definitivo (Celery no llama aquí en los reintentos): lo guarda en la DLQ.

        Con un timeout DURO, Celery llama a este método desde el proceso padre del worker, que no tiene el contexto de
        la petición: el número de intento queda vacío (`attempts` NULL).
        """
        in_request = self.request.id == task_id
        if isinstance(exc, TaskFailure):
            reason, original = exc.reason, exc.__cause__ or exc
        elif classify(exc) == TIMEOUT:
            reason, original = dead_letters.TIME_LIMIT, exc
        else:  # una excepción que la tarea no clasificó: se trata como permanente
            reason, original = dead_letters.PERMANENT_ERROR, exc
        dead_letters.record_failure(
            task_id=task_id,
            task_name=self.name,
            reason=reason,
            error=original,
            attempts=attempt_of(self.request) if in_request else None,
            max_retries=self.max_retries,
            kwargs=kwargs if isinstance(kwargs, dict) else None,
            worker=getattr(self.request, "hostname", None) if in_request else None,
        )


@signals.task_revoked.connect
def _record_expired(sender: Any = None, request: Any = None, expired: bool = False, **_: Any) -> None:
    """Un mensaje caducado (`expires`) no se ejecuta ni llama a `on_failure`: también va a la DLQ (`expired`).

    Las revocaciones manuales (`celery control revoke`) son una decisión de un operador, no un fallo: no se registran.
    """
    if not expired or not getattr(sender, "uses_dead_letters", False) or request is None:
        return
    dead_letters.record_failure(
        task_id=request.id,
        task_name=sender.name,
        reason=dead_letters.EXPIRED,
        error=TaskExpired("El mensaje caducó en la cola antes de que un worker lo empezara"),
        attempts=attempt_of(request),
        max_retries=getattr(sender, "max_retries", None),
        kwargs=getattr(request, "kwargs", None),
        worker=getattr(request, "hostname", None),
    )
