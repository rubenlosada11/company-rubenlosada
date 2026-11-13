"""Reporte Semanal de Desempeño por Almacén y Cliente: resultado y ejecuciones del pipeline (`/reporting`).

Módulo separado de `/telemetry` (BRIEFING de pipelines §6). El cálculo está en `app/reporting/` (flow con subflows);
este router solo valida parámetros, lee las tablas de `reporting` y lanza ejecuciones. Diseño:
`docs/reporting/PIPELINE_DESIGN.md`.

- `GET /reporting/weekly-warehouse-client-performance`: filas de una semana (por defecto, la calculada más reciente).
- `GET /reporting/pipeline-runs/latest`: última ejecución del pipeline y su metadata.
- `POST /reporting/pipeline-runs`: ejecución manual síncrona (solo `admin` o `manager`).

Las lecturas exigen un usuario autenticado. Un fallo de la base es un 503 sin detalles (nunca la cadena de conexión).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError

from app.auth_models import Role
from app.dependencies import CurrentUser, get_current_user
from app.reporting import queries, runs
from app.reporting.flow import PIPELINE_NAME, PipelineAlreadyRunning, PipelineRunFailed, run_weekly_performance
from app.reporting.models import PipelineRun, PipelineRunRequest, WeeklyPerformanceEntry, WeeklyPerformanceReport
from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import WindowError, is_monday

router = APIRouter(prefix="/reporting", tags=["reporting"])

RUNNER_ROLES = {Role.ADMIN, Role.MANAGER}
REPORTING_UNAVAILABLE = "No se ha podido leer el reporte semanal. Inténtalo de nuevo más tarde."
NO_WEEKS_YET = "Aún no hay ninguna semana calculada: ejecuta el pipeline (POST /reporting/pipeline-runs)."
NO_RUNS_YET = "El pipeline semanal todavía no se ha ejecutado nunca."
RUN_FORBIDDEN = "Solo un administrador o un manager puede ejecutar el pipeline."
RUN_IN_PROGRESS = "Ya hay una ejecución del pipeline semanal en curso. Espera a que termine."
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
        "calculada más reciente. Una semana calculada sin actividad devuelve `entries` vacío."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        404: {"description": "Aún no se ha calculado ninguna semana (solo sin `week_start`)"},
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
        week = week_start or queries.latest_week()
        if week is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_WEEKS_YET)
        rows = queries.week_rows(week)
    except ReportingStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORTING_UNAVAILABLE) from None
    return WeeklyPerformanceReport(
        week_start=week,
        computed_at=max((row["computed_at"] for row in rows), default=None),
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
        "Recalcula de forma síncrona e idempotente las `weeks` semanas que terminan en `week_start` (por defecto, las "
        "2 últimas semanas completas) y devuelve la ejecución. Solo `admin` o `manager`. La semana en curso no se "
        "puede calcular."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        403: {"description": "El usuario no es administrador ni manager"},
        409: {"description": "Ya hay una ejecución en curso"},
        422: {"description": "`week_start` no es un lunes, su semana no ha terminado o `weeks` fuera de 1–53"},
        503: {"description": "La ejecución ha fallado (queda registrada como `failed`) o la base no está disponible"},
    },
)
def create_pipeline_run(
    current_user: CurrentUser,
    request: Annotated[PipelineRunRequest | None, Body()] = None,
) -> PipelineRun:
    if current_user.role not in RUNNER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=RUN_FORBIDDEN)
    params = request or PipelineRunRequest()
    try:
        run = run_weekly_performance(
            week_start=params.week_start, weeks=params.weeks, trigger="api", triggered_by=current_user.id
        )
    except WindowError as error:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("body", error.field), "msg": str(error)}]
        ) from None
    except PipelineAlreadyRunning:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=RUN_IN_PROGRESS) from None
    except PipelineRunFailed:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=RUN_FAILED) from None
    except ReportingStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORTING_UNAVAILABLE) from None
    return PipelineRun.model_validate(run)
