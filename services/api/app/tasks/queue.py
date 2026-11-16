"""Productor y consulta de tareas: lo único de Celery que usa la API (nunca ejecuta tareas).

- `submit`: registra el dueño en Redis (`registry.py`), publica el mensaje en el broker y devuelve el `task_id` en
  milisegundos, sin esperar al worker. Si Redis no responde, `TaskQueueUnavailable` (la API responde 503). La API
  **nunca** ejecuta la tarea por su cuenta: sin worker, el mensaje espera en la cola.
- `status`: traduce el estado de Celery al contrato de `GET /tasks/{task_id}`.

Estados de Celery → estados de la API:

    PENDING, RECEIVED → pending    (en la cola; «desconocido» se descarta antes con el registro → 404)
    STARTED           → started    (un worker la está ejecutando: `task_track_started`)
    RETRY             → retrying   (falló de forma transitoria y espera su reintento con backoff)
    SUCCESS           → success    (con `result`)
    FAILURE, REVOKED  → failure    (con `error`: tipo y mensaje controlado, nunca la traza ni datos internos)
"""

import uuid
from dataclasses import dataclass
from typing import Any

import redis
from celery import Task
from celery.result import AsyncResult
from kombu.exceptions import OperationalError as BrokerError

from app.celery_app import MESSAGE_EXPIRES, celery_app
from app.tasks import dead_letters, registry
from app.tasks.base import MAX_RETRIES
from app.tasks.observability import log_event

PENDING = "pending"
STARTED = "started"
RETRYING = "retrying"
SUCCESS = "success"
FAILURE = "failure"

STATES = {
    "PENDING": PENDING,
    "RECEIVED": PENDING,
    "STARTED": STARTED,
    "RETRY": RETRYING,
    "SUCCESS": SUCCESS,
    "FAILURE": FAILURE,
    "REVOKED": FAILURE,
}

# Mensajes de error que ve el cliente: fijos y en español, por tipo de fallo (`TaskFailure.reason`). El detalle técnico
# (excepción original, mensaje completo) solo está en la DLQ y en los logs del worker.
FAILURE_MESSAGES = {
    dead_letters.RETRIES_EXHAUSTED: (
        f"La tarea ha agotado sus {MAX_RETRIES} reintentos ante un fallo transitorio (base de datos no disponible u "
        "otra ejecución del pipeline en curso). Ha quedado registrada en la cola de fallos definitivos (DLQ)."
    ),
    dead_letters.PERMANENT_ERROR: (
        "La tarea ha fallado por un error no recuperable y no se ha reintentado. Ha quedado registrada en la cola de "
        "fallos definitivos (DLQ)."
    ),
    dead_letters.TIME_LIMIT: (
        "La tarea ha superado su tiempo máximo de ejecución. Ha quedado registrada en la cola de fallos definitivos "
        "(DLQ)."
    ),
    dead_letters.EXPIRED: "La tarea ha caducado en la cola sin que ningún worker la empezara.",
}
UNKNOWN_FAILURE = "unknown"

# Errores de conexión con Redis, tanto del cliente directo (registro, result backend) como de kombu (broker).
REDIS_ERRORS = (redis.RedisError, BrokerError, OSError)


class TaskQueueUnavailable(Exception):
    """Redis (broker, result backend o registro) no responde. El mensaje es el tipo de error."""


def submit(task: Task, *, kwargs: dict[str, Any], owner_id: str) -> str:
    """Registra y encola `task` con `kwargs` (solo valores JSON ligeros). Devuelve el `task_id`."""
    task_id = str(uuid.uuid4())
    try:
        registry.register(task_id, task.name, owner_id)
    except registry.TaskRegistryUnavailable as error:
        raise TaskQueueUnavailable(str(error)) from None
    try:
        task.apply_async(kwargs=kwargs, task_id=task_id, expires=int(MESSAGE_EXPIRES.total_seconds()))
    except REDIS_ERRORS as error:
        registry.forget(task_id)
        raise TaskQueueUnavailable(type(error).__name__) from None
    log_event("task_enqueued", task_id=task_id, task_name=task.name)
    return task_id


@dataclass(frozen=True)
class TaskState:
    status: str
    result: Any = None
    error_type: str | None = None
    error_message: str | None = None


def _failure_reason(error: Any) -> str:
    reason = getattr(error, "reason", None)
    if reason in dead_letters.REASONS:
        return reason
    name = type(error).__name__
    if name in ("TimeLimitExceeded", "SoftTimeLimitExceeded"):
        return dead_letters.TIME_LIMIT
    if name == "TaskRevokedError":
        return dead_letters.EXPIRED
    return UNKNOWN_FAILURE


def status(task_id: str) -> TaskState:
    """Estado de la tarea según el result backend. `TaskQueueUnavailable` si Redis no responde."""
    result = AsyncResult(task_id, app=celery_app)
    try:
        celery_state = result.state
        payload = result.result if celery_state in ("SUCCESS", "FAILURE", "REVOKED") else None
    except REDIS_ERRORS as error:
        raise TaskQueueUnavailable(type(error).__name__) from None
    state = STATES.get(celery_state, PENDING)
    if state == SUCCESS:
        return TaskState(status=SUCCESS, result=payload)
    if state == FAILURE:
        reason = _failure_reason(payload)
        if celery_state == "REVOKED" and reason == UNKNOWN_FAILURE:
            reason = dead_letters.EXPIRED
        return TaskState(
            status=FAILURE, error_type=reason, error_message=FAILURE_MESSAGES.get(reason, "La tarea ha fallado.")
        )
    return TaskState(status=state)
