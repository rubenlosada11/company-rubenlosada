"""Reporte Semanal de Desempeño por Almacén y Cliente: resultado y ejecuciones del pipeline (`/reporting`).

Módulo separado de `/telemetry` (BRIEFING de pipelines §6). El cálculo es el flow de Prefect de
`data/pipelines/pipeline.py`, que ejecuta un **worker de Celery** (`app/tasks/reporting.py`, DEV-55) sin duplicar su
lógica: aquí solo se validan parámetros, se leen las tablas de `reporting` y se encolan ejecuciones.
Diseño: `data/pipelines/PIPELINE_DESIGN.md` y `docs/async-tasks.md`.

- `GET /reporting/weekly-warehouse-client-performance`: filas de una semana (por defecto, la calculada más reciente).
- `GET /reporting/pipeline-runs/latest`: última ejecución del pipeline y su metadata.
- `POST /reporting/pipeline-runs`: encola una ejecución manual (solo `admin` o `manager`) y responde 202 con el
  `task_id`; el estado y el resultado, en `GET /tasks/{task_id}`.

Las lecturas exigen un usuario autenticado. Un fallo de la base es un 503 sin detalles (nunca la cadena de conexión).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError

from app.auth_models import Role
from app.dependencies import CurrentUser, get_current_user
from app.reporting import queries, runs
from app.reporting.models import PipelineRun, PipelineRunRequest, WeeklyPerformanceEntry, WeeklyPerformanceReport
from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import WindowError, is_monday, resolve_window
from app.tasks.models import TaskAccepted
from app.tasks.queue import TaskQueueUnavailable
from app.tasks.reporting import enqueue_weekly_performance
from app.telemetry.context import current_context

router = APIRouter(prefix="/reporting", tags=["reporting"])

PIPELINE_NAME = runs.WEEKLY_PERFORMANCE

RUNNER_ROLES = {Role.ADMIN, Role.MANAGER}
REPORTING_UNAVAILABLE = "No se ha podido leer el reporte semanal. Inténtalo de nuevo más tarde."
NO_WEEKS_YET = "Aún no hay ninguna semana calculada: ejecuta el pipeline (POST /reporting/pipeline-runs)."
WEEK_NOT_COMPUTED = "Esa semana no la ha calculado ninguna ejecución correcta del pipeline."
NO_RUNS_YET = "El pipeline semanal todavía no se ha ejecutado nunca."
RUN_FORBIDDEN = "Solo un administrador o un manager puede ejecutar el pipeline."
QUEUE_UNAVAILABLE = "La cola de tareas no está disponible en este momento: no se ha encolado la ejecución."


def _query_error(field: str, message: str) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("query", field), "msg": message}])


@router.get(
    "/weekly-warehouse-client-performance",
    response_model=WeeklyPerformanceReport,
    dependencies=[Depends(get_current_user)],
    summary="Reporte semanal de desempeño por almacén y cliente",
    description=(
        "Volumen de entrada, throughput de salida, quiebres de stock y tasa de discrepancia de cada combinación "
        "almacén/cliente con actividad en la semana ISO `week_start` (un lunes, UTC). Sin `week_start`: la semana "
        "calculada más reciente. Una semana calculada sin actividad devuelve `entries` vacío; una semana que ninguna "
        "ejecución correcta ha calculado, 404 (así no se confunde «sin actividad» con «sin calcular»)."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        404: {"description": "La semana (o ninguna, sin `week_start`) no se ha calculado todavía"},
        422: {"description": "`week_start` no es una fecha o no es un lunes"},
        503: {"description": "No se ha podido leer la tabla del reporte"},
    },
)
def weekly_warehouse_client_performance(
    week_start: Annotated[date | None, Query(description="Lunes de la semana ISO (YYYY-MM-DD).")] = None,
) -> WeeklyPerformanceReport:
    if week_start is not None and not is_monday(week_start):
        raise _query_error("week_start", "week_start debe ser un lunes (inicio de la semana ISO).")
    try:
        week = week_start or runs.latest_covered_week(PIPELINE_NAME)
        if week is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_WEEKS_YET)
        run = runs.latest_covering_run(PIPELINE_NAME, week)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=WEEK_NOT_COMPUTED)
        rows = queries.week_rows(week)
    except ReportingStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORTING_UNAVAILABLE) from None
    return WeeklyPerformanceReport(
        week_start=week,
        computed_at=run["finished_at"],
        run_id=run["id"],
        entries=[WeeklyPerformanceEntry.model_validate(row) for row in rows],
    )


@router.get(
    "/pipeline-runs/latest",
    response_model=PipelineRun,
    dependencies=[Depends(get_current_user)],
    summary="Última ejecución del pipeline semanal",
    description="Estado (`running`, `succeeded`, `failed`), ventana, tiempos, recuentos y error de la última ejecución",
    responses={
        401: {"description": "Sin token o token no válido"},
        404: {"description": "El pipeline no se ha ejecutado nunca"},
        503: {"description": "No se ha podido leer el registro de ejecuciones"},
    },
)
def latest_pipeline_run() -> PipelineRun:
    try:
        run = runs.latest_run(PIPELINE_NAME)
    except ReportingStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORTING_UNAVAILABLE) from None
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_RUNS_YET)
    return PipelineRun.model_validate(run)




@router.post(
    "/pipeline-runs",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Encola una ejecución del pipeline semanal (asíncrona)",
    description=(
        "Valida los parámetros y **encola** el flow de Prefect `weekly-warehouse-client-performance` "
        "(data/pipelines/pipeline.py) para que lo ejecute un worker de Celery; responde al momento con el `task_id`, "
        "sin esperar al cálculo. El estado y el resultado (la ejecución registrada, con `outcome`) se consultan en "
        "`GET /tasks/{task_id}` (cabecera `Location`). Recalcula de forma idempotente las `weeks` semanas que terminan "
        "en `week_start` (por defecto, las 2 últimas semanas completas). Solo `admin` o `manager`. La semana en curso "
        "no se puede calcular. Si ya hay otra ejecución en curso, la tarea se reintenta con backoff (2, 4 y 8 s)."
    ),
    responses={
        202: {"description": "Encolada: `{\"task_id\": …}`"},
        401: {"description": "Sin token o token no válido"},
        403: {"description": "El usuario no es administrador ni manager"},
        422: {"description": "`week_start` no es un lunes, su semana no ha terminado o `weeks` fuera de 1–53"},
        503: {"description": "La cola de tareas (Redis) no está disponible: no se ha encolado nada"},
    },
)
def create_pipeline_run(
    current_user: CurrentUser,
    response: Response,
    request: Annotated[PipelineRunRequest | None, Body()] = None,
) -> TaskAccepted:
    if current_user.role not in RUNNER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=RUN_FORBIDDEN)
    params = request or PipelineRunRequest()
    try:
        # La ventana se fija AHORA: el worker (y cada reintento) calcula exactamente estas semanas.
        window = resolve_window(params.week_start, params.weeks)
    except WindowError as error:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("body", error.field), "msg": str(error)}]
        ) from None
    context = current_context()
    try:
        task_id = enqueue_weekly_performance(
            week_start=window.last,
            weeks=params.weeks,
            owner_id=current_user.id,
            # Mismo X-Request-Id que la respuesta: une la petición, la tarea, sus logs y la ejecución.
            request_id=context.request_id if context else None,
        )
    except TaskQueueUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=QUEUE_UNAVAILABLE) from None
    response.headers["Location"] = f"/tasks/{task_id}"
    return TaskAccepted(task_id=task_id)
