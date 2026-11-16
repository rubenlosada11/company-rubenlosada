"""Tarea de negocio: el Reporte Semanal de Desempeño por Almacén y Cliente, ejecutado por un worker de Celery.

Antes, `POST /reporting/pipeline-runs` ejecutaba el flow de Prefect dentro de la petición HTTP (segundos o minutos,
según la base y sus reintentos). Ahora la API solo valida y encola (`enqueue_weekly_performance`) y el worker ejecuta
**el mismo flow** (`data/pipelines/pipeline.py`, vía `app/reporting/runner.py`): sin duplicar lógica.

- **Argumentos ligeros:** la semana final (`week_start`, ISO), el número de semanas y dos identificadores de
  trazabilidad (usuario y `X-Request-Id`). Los eventos se leen de la base en el worker. La API resuelve la ventana al
  encolar, así cada reintento calcula exactamente las mismas semanas aunque pase un lunes entre medias.
- **Errores** (`DeadLetterTask.retry_or_fail`):
  - transitorios → reintento con backoff (2, 4, 8 s): `PipelineAlreadyRunning` (otro proceso, p. ej. el cron, tiene
    una ejecución en curso) y los fallos transitorios de la base que el pipeline no pudo superar con sus propios
    reintentos (`ReportingStorageError.transient`, también como causa de `PipelineRunFailed`);
  - permanentes → sin reintento: ventana no válida, pipeline no disponible en el despliegue, tabla inexistente, un
    bug en la transformación (`PipelineRunFailed` con causa permanente)…
- **Resultado:** la ejecución registrada (`PipelineRun`, el mismo JSON que devolvía el endpoint síncrono), que
  `GET /tasks/{task_id}` devuelve en `result`.

Hay dos niveles de reintento y no se pisan: Prefect reintenta **cada etapa** (extract 2/10/30 s, load 5/15 s) dentro de
una ejecución; Celery reintenta **la tarea entera** solo si la ejecución completa falló por un motivo transitorio.
"""

import uuid
from datetime import date
from typing import Any

from app.celery_app import celery_app
from app.reporting import runner
from app.reporting.models import PipelineRun
from app.tasks import queue
from app.tasks.base import DeadLetterTask

WEEKLY_PERFORMANCE_TASK = "reporting.run_weekly_performance"


@celery_app.task(bind=True, base=DeadLetterTask, name=WEEKLY_PERFORMANCE_TASK)
def run_weekly_performance(
    self: DeadLetterTask,
    week_start: str,
    weeks: int,
    triggered_by: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    try:
        pipeline = runner.load_pipeline()
    except runner.PipelineUnavailable as error:
        self.retry_or_fail(error, transient=False)
    try:
        run = pipeline.run_weekly_performance(
            week_start=date.fromisoformat(week_start),
            weeks=weeks,
            trigger="api",
            triggered_by=triggered_by,
            request_id=uuid.UUID(request_id) if request_id else None,
        )
    except pipeline.PipelineAlreadyRunning as error:
        self.retry_or_fail(error, transient=True)
    except Exception as error:
        self.retry_or_fail(error)
    return PipelineRun.model_validate(run).model_dump(mode="json")


def enqueue_weekly_performance(*, week_start: date, weeks: int, owner_id: str, request_id: str | None) -> str:
    """Encola la ejecución y devuelve su `task_id` (productor). `queue.TaskQueueUnavailable` si Redis no responde."""
    return queue.submit(
        run_weekly_performance,
        kwargs={
            "week_start": week_start.isoformat(),
            "weeks": weeks,
            "triggered_by": owner_id,
            "request_id": request_id,
        },
        owner_id=owner_id,
    )
