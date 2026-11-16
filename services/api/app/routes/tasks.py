"""Consulta de tareas asíncronas (`/tasks`, DEV-55). Documentación: docs/async-tasks.md.

- `GET /tasks/{task_id}`: estado de una tarea encolada por el usuario autenticado (`pending`, `started`, `retrying`,
  `success`, `failure`) y su resultado o error.
- `GET /tasks/dead-letters`: últimos fallos definitivos de la DLQ (solo `admin`).

Un `task_id` que la API no ha registrado (inventado, caducado) y uno de **otro usuario** responden igual, 404: así no
se puede averiguar qué tareas existen. Celery por sí solo devolvería `PENDING` para cualquier id.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.auth_models import Role
from app.dependencies import CurrentUser
from app.tasks import dead_letters, queue, registry
from app.tasks.models import DeadLetter, TaskError, TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])

TASK_NOT_FOUND = "No existe ninguna tarea tuya con ese identificador (o ya ha caducado)."
QUEUE_UNAVAILABLE = "La cola de tareas no está disponible en este momento. Inténtalo de nuevo más tarde."
DEAD_LETTERS_FORBIDDEN = "Solo un administrador puede consultar la cola de fallos definitivos."
DEAD_LETTERS_UNAVAILABLE = "No se ha podido leer la cola de fallos definitivos. Inténtalo de nuevo más tarde."


@router.get(
    "/dead-letters",
    response_model=list[DeadLetter],
    summary="Fallos definitivos (DLQ)",
    description=(
        "Tareas que han fallado definitivamente (reintentos agotados, error permanente, tiempo máximo superado o "
        "caducadas), de la más reciente a la más antigua. Persisten en la base de datos (`task_dead_letters`). Solo "
        "`admin`."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        403: {"description": "El usuario no es administrador"},
        503: {"description": "No se ha podido leer la tabla de la DLQ"},
    },
)
def list_dead_letters(
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200, description="Máximo de registros.")] = 50,
) -> list[DeadLetter]:
    if current_user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=DEAD_LETTERS_FORBIDDEN)
    try:
        rows = dead_letters.latest(limit)
    except dead_letters.DeadLetterStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=DEAD_LETTERS_UNAVAILABLE) from None
    return [DeadLetter.model_validate(row) for row in rows]


@router.get(
    "/{task_id}",
    response_model=TaskStatus,
    summary="Estado de una tarea asíncrona",
    description=(
        "Estado real de Celery traducido a `pending`, `started`, `retrying`, `success` o `failure`. Con `success`, "
        "`result` lleva el resultado; con `failure`, `error` lleva el tipo de fallo y un mensaje controlado (el "
        "detalle técnico queda en la DLQ). Solo el usuario que encoló la tarea puede consultarla."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        404: {"description": "Id desconocido, caducado o de otro usuario"},
        422: {"description": "`task_id` no es un UUID"},
        503: {"description": "Redis no responde"},
    },
)
def get_task(
    task_id: Annotated[uuid.UUID, Path(description="Identificador devuelto por el endpoint productor (202).")],
    current_user: CurrentUser,
) -> TaskStatus:
    key = str(task_id)
    try:
        record = registry.lookup(key)
        if record is None or record.owner_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)
        state = queue.status(key)
    except (registry.TaskRegistryUnavailable, queue.TaskQueueUnavailable):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=QUEUE_UNAVAILABLE) from None
    return TaskStatus(
        task_id=key,
        task_name=record.task_name,
        status=state.status,
        submitted_at=record.submitted_at,
        result=state.result if isinstance(state.result, dict) else None,
        error=TaskError(type=state.error_type, message=state.error_message) if state.error_type else None,
    )
