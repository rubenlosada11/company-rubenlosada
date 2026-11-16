"""Registro de las tareas encoladas por la API: quién encoló cada `task_id` y qué tarea es (en Redis).

Celery no distingue «en cola» de «no existe»: `AsyncResult(id).state` es `PENDING` para los dos. Además, su result
backend no guarda quién lanzó la tarea. Por eso la API, al encolar, apunta en Redis:

    trackflow:tasks:<task_id> → {"task_name": …, "owner_id": …, "submitted_at": …}   (caduca con el resultado)

y `GET /tasks/{task_id}` responde 404 si el id no está registrado (desconocido o caducado) o si es de otro usuario (sin
revelar que existe). Va en el mismo Redis que el broker (`REDIS_URL`): sin tablas ni servicios nuevos.
"""

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

from app.celery_app import CONNECT_TIMEOUT_SECONDS, RESULT_TTL, get_redis_url

KEY_PREFIX = "trackflow:tasks:"
SOCKET_TIMEOUT_SECONDS = 5


class TaskRegistryUnavailable(Exception):
    """Redis no responde: no se puede registrar ni consultar una tarea. El mensaje es el tipo de error."""


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    task_name: str
    owner_id: str
    submitted_at: datetime


_clients: dict[str, redis.Redis] = {}
_clients_lock = threading.Lock()


def get_client() -> redis.Redis:
    """Cliente de Redis de `REDIS_URL` (uno por URL; redis-py mantiene su propio pool de conexiones)."""
    url = get_redis_url()
    with _clients_lock:
        client = _clients.get(url)
        if client is None:
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
                socket_timeout=SOCKET_TIMEOUT_SECONDS,
                decode_responses=True,
            )
            _clients[url] = client
    return client


def _key(task_id: str) -> str:
    return KEY_PREFIX + task_id


def register(task_id: str, task_name: str, owner_id: str) -> TaskRecord:
    """Apunta la tarea antes de encolarla. `TaskRegistryUnavailable` si Redis no responde."""
    record = TaskRecord(task_id=task_id, task_name=task_name, owner_id=owner_id, submitted_at=datetime.now(UTC))
    value = json.dumps(
        {"task_name": task_name, "owner_id": owner_id, "submitted_at": record.submitted_at.isoformat()}
    )
    try:
        get_client().set(_key(task_id), value, ex=int(RESULT_TTL.total_seconds()))
    except redis.RedisError as error:
        raise TaskRegistryUnavailable(type(error).__name__) from None
    return record


def lookup(task_id: str) -> TaskRecord | None:
    """Registro de la tarea, o `None` si no existe o ha caducado. `TaskRegistryUnavailable` si Redis no responde."""
    try:
        value = get_client().get(_key(task_id))
    except redis.RedisError as error:
        raise TaskRegistryUnavailable(type(error).__name__) from None
    if value is None:
        return None
    data = json.loads(value)
    return TaskRecord(
        task_id=task_id,
        task_name=data["task_name"],
        owner_id=data["owner_id"],
        submitted_at=datetime.fromisoformat(data["submitted_at"]),
    )


def forget(task_id: str) -> None:
    """Borra el registro (la tarea no se llegó a encolar). Sin errores: si Redis no responde, caducará solo."""
    try:
        get_client().delete(_key(task_id))
    except redis.RedisError:
        pass
