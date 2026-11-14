"""Reporte Semanal de Desempeño por Almacén y Cliente: resultado y ejecuciones del pipeline (`/reporting`).

Módulo separado de `/telemetry` (BRIEFING de pipelines §6). El cálculo es el flow de Prefect de
`data/pipelines/pipeline.py`, que este router importa (`app/reporting/runner.py`) sin duplicar su lógica: aquí solo se
validan parámetros, se leen las tablas de `reporting` y se lanzan ejecuciones. Diseño:
`data/pipelines/PIPELINE_DESIGN.md`.

- `GET /reporting/weekly-warehouse-client-performance`: filas de una semana (por defecto, la calculada más reciente).
- `GET /reporting/pipeline-runs/latest`: última ejecución del pipeline y su metadata.
- `POST /reporting/pipeline-runs`: ejecución manual síncrona del flow (solo `admin` o `manager`).

Las lecturas exigen un usuario autenticado. Un fallo de la base es un 503 sin detalles (nunca la cadena de conexión).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError

from app.auth_models import Role
from app.dependencies import CurrentUser, get_current_user
from app.reporting import queries, runner, runs
from app.reporting.models import PipelineRun, PipelineRunRequest, WeeklyPerformanceEntry, WeeklyPerformanceReport
from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import WindowError, is_monday
from app.telemetry.context import current_context

router = APIRouter(prefix="/reporting", tags=["reporting"])

PIPELINE_NAME = runs.WEEKLY_PERFORMANCE

RUNNER_ROLES = {Role.ADMIN, Role.MANAGER}
REPORTING_UNAVAILABLE = "No se ha podido leer el reporte semanal. Inténtalo de nuevo más tarde."
NO_WEEKS_YET = "Aún no hay ninguna semana calculada: ejecuta el pipeline (POST /reporting/pipeline-runs)."
WEEK_NOT_COMPUTED = "Esa semana no la ha calculado ninguna ejecución correcta del pipeline."
NO_RUNS_YET = "El pipeline semanal todavía no se ha ejecutado nunca."
RUN_FORBIDDEN = "Solo un administrador o un manager puede ejecutar el pipeline."
RUN_IN_PROGRESS = "Ya hay una ejecución del pipeline semanal en curso. Espera a que termine."
PIPELINE_UNAVAILABLE = "El pipeline no está disponible en este despliegue (falta data/pipelines o Prefect)."
RUN_FAILED = (
    "La ejecución del pipeline ha fallado y ha quedado registrada (GET /reporting/pipeline-runs/latest). "
    "El reporte no ha cambiado."
)


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
    response_model=PipelineRun,
    status_code=status.HTTP_201_CREATED,
    summary="Ejecuta el pipeline semanal (manual)",
    description=(
        "Ejecuta de forma síncrona el flow de Prefect `weekly-warehouse-client-performance` "
        "(data/pipelines/pipeline.py): "
        "recalcula de forma idempotente las `weeks` semanas que terminan en `week_start` (por defecto, las 2 últimas "
        "semanas completas) y devuelve la ejecución. `outcome` = `partial` si falló una etapa opcional (el reporte se "
        "cargó igual). Solo `admin` o `manager`. La semana en curso no se puede calcular."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        403: {"description": "El usuario no es administrador ni manager"},
        409: {"description": "Ya hay una ejecución en curso"},
        422: {"description": "`week_start` no es un lunes, su semana no ha terminado o `weeks` fuera de 1–53"},
        503: {
            "description": (
                "La ejecución ha fallado (queda registrada como `failed`), la base no está disponible o el pipeline no "
                "está en este despliegue"
            )
        },
    },
)
def create_pipeline_run(
    current_user: CurrentUser,
    request: Annotated[PipelineRunRequest | None, Body()] = None,
) -> PipelineRun:
    if current_user.role not in RUNNER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=RUN_FORBIDDEN)
    params = request or PipelineRunRequest()
    context = current_context()
    try:
        pipeline = runner.load_pipeline()
    except runner.PipelineUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=PIPELINE_UNAVAILABLE) from None
    try:
        run = pipeline.run_weekly_performance(
            week_start=params.week_start,
            weeks=params.weeks,
            trigger="api",
            triggered_by=current_user.id,
            # Mismo X-Request-Id que la respuesta: une la petición, sus logs y la ejecución.
            request_id=uuid.UUID(context.request_id) if context else None,
        )
    except WindowError as error:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("body", error.field), "msg": str(error)}]
        ) from None
    except pipeline.PipelineAlreadyRunning:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=RUN_IN_PROGRESS) from None
    except pipeline.PipelineRunFailed:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=RUN_FAILED) from None
    except ReportingStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORTING_UNAVAILABLE) from None
    return PipelineRun.model_validate(run)
