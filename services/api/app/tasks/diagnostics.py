"""Tarea mínima de comprobación: demuestra que API, broker y worker se comunican sin tocar datos de negocio.

    uv run python -c "from app.tasks.diagnostics import ping; print(ping.delay().get(timeout=10))"
    docker compose exec backend python -c "from app.tasks.diagnostics import ping; print(ping.delay().get(timeout=10))"

`delay_seconds` (0–60) simula una operación lenta: sirve para ver una tarea `started` en Flower o en
`GET /tasks/{task_id}` y para probar el límite de tiempo suave (`ping.apply_async(kwargs=…, soft_time_limit=1)`).
`simulate_hang=True` ignora el límite suave, como una llamada bloqueada en código C que no atiende la señal, para
comprobar que el límite DURO mata el proceso hijo (`soft_time_limit=1, time_limit=2`). No se expone por HTTP.
"""

import time
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import DeadLetterTask

PING_TASK = "diagnostics.ping"
MAX_DELAY_SECONDS = 60


@celery_app.task(bind=True, base=DeadLetterTask, name=PING_TASK, max_retries=0)
def ping(self: DeadLetterTask, delay_seconds: float = 0, simulate_hang: bool = False) -> dict[str, Any]:
    if not isinstance(delay_seconds, (int, float)) or not 0 <= delay_seconds <= MAX_DELAY_SECONDS:
        self.retry_or_fail(ValueError(f"delay_seconds debe estar entre 0 y {MAX_DELAY_SECONDS}"), transient=False)
    deadline = time.monotonic() + delay_seconds
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            time.sleep(remaining)
        except SoftTimeLimitExceeded as error:  # límite de tiempo suave superado
            if not simulate_hang:
                self.retry_or_fail(error)
    return {"pong": True, "worker": self.request.hostname, "delay_seconds": delay_seconds}
