"""Logs estructurados del ciclo de vida de las tareas: una línea JSON por evento, con `task_id`, intento y duración.

Se conectan a las señales de Celery, así cualquier tarea queda registrada sin repetir código:

- `task_started` (`task_prerun`): empieza un intento.
- `task_finished` (`task_postrun`): termina un intento, con su estado (`SUCCESS`, `RETRY`, `FAILURE`) y duración.

Los demás eventos los emite el código que los decide: `task_enqueued` (API, `queue.py`), `task_retry_scheduled` y
`task_failed_permanently` (`base.py`), `dead_letter_recorded` / `dead_letter_duplicate` / `dead_letter_not_persisted`
(`dead_letters.py`).

Ejemplo (línea del worker):

    {"event": "task_finished", "task_id": "…", "task_name": "reporting.run_weekly_performance", "attempt": 2,
     "state": "RETRY", "duration_ms": 41}

Nunca se registran los argumentos completos ni datos de negocio: solo identificadores, estados, tipos de error y
tiempos.
"""

import json
import logging
import time
from typing import Any

from celery import signals

logger = logging.getLogger("trackflow.tasks")

# Inicio de cada intento en este proceso (task_id → perf_counter), para medir su duración.
_started: dict[str, float] = {}


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Escribe un evento como una línea JSON en el logger `trackflow.tasks`."""
    logger.log(level, json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))


def attempt_of(request: Any) -> int | None:
    """Número de intento (1 = intento inicial; 2-4 = reintentos) de la petición en curso, si se conoce."""
    retries = getattr(request, "retries", None)
    return retries + 1 if isinstance(retries, int) else None


@signals.task_prerun.connect
def _task_started(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    if task_id is None or task is None:
        return
    _started[task_id] = time.perf_counter()
    log_event(
        "task_started",
        task_id=task_id,
        task_name=task.name,
        attempt=attempt_of(task.request),
        worker=getattr(task.request, "hostname", None),
    )


@signals.task_postrun.connect
def _task_finished(task_id: str | None = None, task: Any = None, state: str | None = None, **_: Any) -> None:
    if task_id is None or task is None:
        return
    began = _started.pop(task_id, None)
    level = {"RETRY": logging.WARNING, "FAILURE": logging.ERROR}.get(state or "", logging.INFO)
    log_event(
        "task_finished",
        level,
        task_id=task_id,
        task_name=task.name,
        attempt=attempt_of(task.request),
        state=state,
        duration_ms=round((time.perf_counter() - began) * 1000) if began is not None else None,
    )
