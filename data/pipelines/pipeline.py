"""Pipeline de Desempeño de Negocio Resiliente — Reporte Semanal de Desempeño por Almacén y Cliente (Prefect 3).

Punto de entrada y definición de los flows. Diseño: `data/pipelines/PIPELINE_DESIGN.md` (§18, implementación con
Prefect). Recorrido de los datos:

    telemetry_events (solo lectura)
        │  extract-telemetry-events      reintentos ante fallos transitorios
        ▼
    transform-weekly-kpis              validate → aggregate → coherencia; caché (cache_key_fn + cache_expiration)
        │
        ├─▶ observe-source               OPCIONAL (return_state=True): si falla, aviso y ejecución «parcial»
        ▼
    load-weekly-kpis                   CRÍTICA (return_state=True): si falla, la ejecución es «failed»
        │                              upsert sobre unique (warehouse, client_id, week_start), una transacción
        ├─▶ write-eval-snapshot          OPCIONAL (return_state=True): JSON en data/eval/
        ▼
    reporting.weekly_warehouse_client_performance  +  reporting.pipeline_runs (registro de la ejecución)

Ejecución desde la raíz del monorepo (con el entorno de `services/api`, que es donde está instalado Prefect):

    uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py
    uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py --weeks 4
    uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py --dry-run

(`--week-start 2026-11-02` fija la semana más reciente a calcular; por defecto, la última completa.)

o, con el entorno virtual de `services/api` activado y las variables en el entorno, `python data/pipelines/pipeline.py`.
Sin `DATABASE_URL` usa la base SQLite local de la API. Códigos de salida: 0 correcta (también parcial), 1 fallida,
2 parámetros no válidos o ejecución ya en curso.

La API (`POST /reporting/pipeline-runs`) importa este módulo y llama a `run_weekly_performance`: el mismo flow, sin
duplicar la lógica.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

# --- Arranque: rutas de importación y configuración de Prefect (antes de importar nada del proyecto ni Prefect) ----
# `python data/pipelines/pipeline.py` solo añade esta carpeta a sys.path: se añaden la raíz (paquete `data`) y la API
# (paquete `app`, capa de acceso a la base que comparte con el pipeline). Se añaden al final para no tapar nada.
REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
for _path in (REPO_ROOT, API_ROOT):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))

# Resultados persistidos de Prefect (la caché de la transformación) en data/raw/prefect-results/ (ignorado en git): son
# ficheros intermedios del pipeline. Y sin analítica de uso del servidor temporal de Prefect: no salen datos de
# ejecución hacia terceros. `setdefault`: una configuración explícita del entorno siempre manda.
os.environ.setdefault("PREFECT_RESULTS_LOCAL_STORAGE_PATH", str(REPO_ROOT / "data" / "raw" / "prefect-results"))
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")

import pandas as pd  # noqa: E402
from prefect import flow, get_run_logger, task  # noqa: E402
from prefect.cache_policies import NO_CACHE  # noqa: E402
from prefect.runtime import flow_run as current_flow_run  # noqa: E402

from app.reporting import runs  # noqa: E402
from app.reporting.tables import ReportingStorageError  # noqa: E402
from app.reporting.weeks import DEFAULT_WEEKS, WeekWindow, WindowError, resolve_window  # noqa: E402
from app.telemetry.config import get_environment  # noqa: E402
from data.pipelines.weekly_performance.evaluation import write_snapshot  # noqa: E402
from data.pipelines.weekly_performance.extract import extract_events  # noqa: E402
from data.pipelines.weekly_performance.load import LoadResult, load_rows  # noqa: E402
from data.pipelines.weekly_performance.observe import UNAVAILABLE, observe  # noqa: E402
from data.process.weekly_performance.transform import (  # noqa: E402
    CODE_VERSION,
    Transformation,
    fingerprint_events,
    transform_events,
)

PIPELINE_NAME = runs.WEEKLY_PERFORMANCE
Trigger = Literal["api", "cli"]
Outcome = Literal["succeeded", "partial", "failed"]


class PipelineAlreadyRunning(RuntimeError):
    """Ya hay una ejecución de este pipeline en curso (en este proceso o en otro: `cron` y API)."""


class PipelineRunFailed(RuntimeError):
    """La ejecución ha fallado y ha quedado registrada como `failed`. `run` es su registro (si se pudo leer)."""

    def __init__(self, run: dict[str, Any] | None, error: str) -> None:
        super().__init__(error)
        self.run = run
        self.error = error


# --- Reintentos ------------------------------------------------------------------------------------------------------
# Solo se reintentan los fallos **transitorios** (`ReportingStorageError.transient`: conexión cortada, base
# reiniciando, demasiadas conexiones, bloqueo). Un error permanente (tabla inexistente, migración sin aplicar,
# contraseña errónea, un bug) no se arregla esperando: falla a la primera y queda registrado.
#
# - extract (lectura de telemetry_events): 3 reintentos a los 2, 10 y 30 s (~42 s en total). Un corte del pooler de
#   Supabase o un reinicio de la base se resuelve en segundos; si dura más de un minuto ya no es transitorio y es mejor
#   fallar y dejar que la ventana de 2 semanas de la siguiente ejecución rellene la semana (autorreparación, §7).
# - load (escritura del reporte): 2 reintentos a los 5 y 15 s. Es una única transacción idempotente: un intento fallido
#   no deja nada escrito, así que reintentar es seguro. Menos intentos que la lectura: el cálculo ya está hecho y
#   conviene registrar pronto un fallo persistente.
# - registro de ejecuciones y observe: 2 y 1 reintentos cortos (escrituras de una fila; lecturas opcionales).
# `retry_jitter_factor` reparte las esperas para que dos procesos no reintenten a la vez contra la misma base.
EXTRACT_RETRY_DELAYS = [2, 10, 30]
LOAD_RETRY_DELAYS = [5, 15]
REGISTRY_RETRY_DELAYS = [1, 5]
OBSERVE_RETRY_DELAYS = [2]
RETRY_JITTER = 0.2


def retry_if_transient(task, task_run, state) -> bool:
    """`retry_condition_fn` de Prefect: reintenta solo si la task falló con un `ReportingStorageError` transitorio."""
    try:
        state.result()
    except ReportingStorageError as error:
        return error.transient
    except Exception:
        return False
    return False


# --- Caché de la transformación -------------------------------------------------------------------------------------
# La clave identifica TODO lo que determina el resultado de `transform-weekly-kpis`, y nada más:
#   1. `source`: huella SHA-256 del contenido de los eventos extraídos (id, tipo, fecha y tags de cada uno). Un evento
#      tardío, nuevo o distinto cambia la huella → otra clave → se recalcula. Nunca se sirve un KPI obsoleto.
#   2. `weeks`: las semanas de la ventana (la agregación descarta lo que cae fuera).
#   3. `environment`: el entorno de los eventos (ya va implícito en la huella; se incluye por claridad).
#   4. `code`: huella del código de data/process/weekly_performance/. Cambiar una regla o una fórmula invalida la
#      caché aunque los datos sean los mismos.
# Mismos datos + mismas semanas + mismo código ⇒ mismo resultado (la transformación es pura), así que reutilizarlo es
# correcto por construcción. Caducidad: 1 día. La caché sirve para repeticiones cercanas sobre los mismos datos (un
# reintento manual tras un fallo de carga, la segunda ejecución de la prueba de idempotencia, un `--dry-run` seguido de
# la ejecución real); para la ejecución del lunes siguiente los datos ya habrán cambiado. Caducar pronto evita que se
# acumulen ficheros en data/raw/prefect-results/. Se invalida si: cambian los eventos, la ventana, el entorno o el
# código; pasa 1 día; o se borra esa carpeta.
TRANSFORM_CACHE_EXPIRATION = timedelta(days=1)


@dataclass(frozen=True)
class Extraction:
    """Salida de la extracción: eventos crudos, entorno y huella de su contenido (entrada de la clave de caché)."""

    events: pd.DataFrame
    environment: str
    fingerprint: str

    @property
    def count(self) -> int:
        return len(self.events)


def transform_cache_key(context, parameters: dict[str, Any]) -> str:
    """`cache_key_fn` de `transform-weekly-kpis`: ver el comentario de arriba."""
    extraction: Extraction = parameters["extraction"]
    material = {
        "source": extraction.fingerprint,
        "environment": extraction.environment,
        "weeks": [week.isoformat() for week in parameters["weeks"]],
        "code": CODE_VERSION,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return f"weekly-kpis-{digest}"


# --- Tasks -----------------------------------------------------------------------------------------------------------
# Las funciones de cada etapa se llaman por su nombre global en el momento de ejecutarse (los tests las sustituyen).


@task(
    name="register-run",
    retries=len(REGISTRY_RETRY_DELAYS),
    retry_delay_seconds=REGISTRY_RETRY_DELAYS,
    retry_condition_fn=retry_if_transient,
    cache_policy=NO_CACHE,
)
def register_run(
    run_id: uuid.UUID,
    window: WeekWindow,
    environment: str,
    trigger: Trigger,
    triggered_by: str | None,
    request_id: uuid.UUID | None,
    started_at: datetime,
) -> uuid.UUID:
    """Abre el registro de la ejecución (`running`). `PipelineAlreadyRunning` si otro proceso tiene una en curso."""
    try:
        return runs.start_run(
            pipeline=PIPELINE_NAME,
            trigger=trigger,
            triggered_by=triggered_by,
            environment=environment,
            week_from=window.first,
            week_to=window.last,
            started_at=started_at,
            request_id=request_id,
            run_id=run_id,
        )
    except runs.RunInProgress:
        raise PipelineAlreadyRunning("Ya hay una ejecución del pipeline semanal en curso.") from None


@task(
    name="extract-telemetry-events",
    retries=len(EXTRACT_RETRY_DELAYS),
    retry_delay_seconds=EXTRACT_RETRY_DELAYS,
    retry_jitter_factor=RETRY_JITTER,
    retry_condition_fn=retry_if_transient,
    cache_policy=NO_CACHE,
)
def extract_task(window: WeekWindow, environment: str) -> Extraction:
    """Eventos de los 4 tipos del BRIEFING del entorno y la ventana (solo lectura) y su huella."""
    events = extract_events(window, environment)
    extraction = Extraction(events=events, environment=environment, fingerprint=fingerprint_events(events))
    get_run_logger().info("%d eventos extraídos (huella %s)", extraction.count, extraction.fingerprint[:12])
    return extraction


@task(
    name="transform-weekly-kpis",
    cache_key_fn=transform_cache_key,
    cache_expiration=TRANSFORM_CACHE_EXPIRATION,
)
def transform_task(extraction: Extraction, weeks: list[date]) -> Transformation:
    """validate → aggregate → controles de coherencia (data/process). Pura: su resultado se puede cachear."""
    transformation = transform_events(extraction.events, weeks)
    logger = get_run_logger()
    if transformation.rejected:
        logger.warning("Eventos rechazados por calidad: %s", transformation.rejected)
    logger.info("%d filas del reporte calculadas", len(transformation.rows))
    return transformation


@task(
    name="observe-source",
    retries=len(OBSERVE_RETRY_DELAYS),
    retry_delay_seconds=OBSERVE_RETRY_DELAYS,
    retry_condition_fn=retry_if_transient,
    cache_policy=NO_CACHE,
)
def observe_task(window: WeekWindow, extraction: Extraction) -> dict[str, Any]:
    """Salud del origen y cobertura frente al inventario (solo lectura). Opcional: el flow tolera su fallo."""
    return observe(window, extraction.environment, extraction.events)


@task(
    name="load-weekly-kpis",
    retries=len(LOAD_RETRY_DELAYS),
    retry_delay_seconds=LOAD_RETRY_DELAYS,
    retry_jitter_factor=RETRY_JITTER,
    retry_condition_fn=retry_if_transient,
    cache_policy=NO_CACHE,
)
def load_task(rows: list[dict], window: WeekWindow, run_id: uuid.UUID) -> LoadResult:
    """Upsert idempotente + reconciliación de las semanas de la ventana, en una transacción. Crítica."""
    return load_rows(rows, window, computed_at=datetime.now(UTC), run_id=run_id)


@task(name="write-eval-snapshot", cache_policy=NO_CACHE)
def eval_snapshot_task(run_id: uuid.UUID, payload: dict[str, Any]) -> str:
    """Snapshot JSON de la ejecución en data/eval/ (opcional). Devuelve la ruta, relativa a la raíz si está dentro."""
    path = write_snapshot(str(run_id), payload)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


@task(
    name="close-run",
    retries=len(REGISTRY_RETRY_DELAYS),
    retry_delay_seconds=REGISTRY_RETRY_DELAYS,
    retry_condition_fn=retry_if_transient,
    cache_policy=NO_CACHE,
)
def close_run(run_id: uuid.UUID, values: dict[str, Any]) -> None:
    """Cierra el registro de la ejecución con su estado, tiempos, recuentos y estadísticas."""
    runs.finish_run(run_id, **values)


# --- Flows -----------------------------------------------------------------------------------------------------------


def _error_kind(error: BaseException) -> str:
    """Tipo de error para el registro: nunca el mensaje (podría llevar datos o la cadena de conexión)."""
    if isinstance(error, ReportingStorageError):
        return str(error)
    return type(error).__name__


def _current_run_id() -> uuid.UUID:
    """Id del *flow run* de Prefect: es también el id de la ejecución en `reporting.pipeline_runs`."""
    return uuid.UUID(str(current_flow_run.id))


def _observations(state, logger) -> tuple[dict[str, Any], bool]:
    """Decisión sobre la etapa opcional `observe-source`: sus señales si terminó bien; si no, el aviso y `degraded`."""
    if state.is_completed():
        return state.result(), False
    logger.warning("observe-source no disponible (%s): se continúa sin señales del origen", state.name)
    return {"warnings": [UNAVAILABLE]}, True


@flow(name="weekly-warehouse-client-performance", persist_result=False)
def weekly_performance_flow(
    week_from: date,
    week_to: date,
    trigger: Trigger = "cli",
    triggered_by: str | None = None,
    request_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """ETL completo de las semanas `[week_from, week_to]` (lunes, ya validadas) y registro de la ejecución.

    Devuelve el registro (`status = succeeded`; `stats.outcome` = `succeeded` o `partial`). Lanza
    `PipelineAlreadyRunning` o `ReportingStorageError` si no se puede ni registrar, y `PipelineRunFailed` si falla una
    etapa crítica (extract, transform o load): la ejecución queda `failed` con su última fase y el reporte, sin cambios.
    """
    logger = get_run_logger()
    window = WeekWindow(first=week_from, last=week_to)
    environment = get_environment()
    run_id = _current_run_id()
    started_at = datetime.now(UTC)
    began = time.perf_counter()

    def elapsed_ms() -> int:
        return round((time.perf_counter() - began) * 1000)

    def fail(error: BaseException) -> PipelineRunFailed:
        kind = _error_kind(error)
        logger.error("Ejecución %s fallida: %s", run_id, kind)
        try:
            runs.finish_run(
                run_id, status="failed", finished_at=datetime.now(UTC), duration_ms=elapsed_ms(), error=kind
            )
            run = runs.get_run(run_id)
        except ReportingStorageError:
            run = None
        return PipelineRunFailed(run, kind)

    register_run(run_id, window, environment, trigger, triggered_by, request_id, started_at)
    logger.info(
        "Ejecución %s (%s, %s, request %s): semanas %s → %s",
        run_id,
        trigger,
        environment,
        request_id or "-",
        window.first.isoformat(),
        window.last.isoformat(),
    )
    degraded: list[str] = []
    try:
        extraction = extract_task(window, environment)
        runs.set_phase(run_id, "extracted")
        transform_state = transform_task(extraction, window.weeks, return_state=True)
        transformation: Transformation = transform_state.result()  # si falló, relanza su excepción
        cache = "hit" if transform_state.name == "Cached" else "miss"
        runs.set_phase(run_id, "aggregated")

        # Etapa OPCIONAL: su fallo no detiene el flujo; la ejecución sigue y se marcará como parcial.
        observations, observe_failed = _observations(observe_task(window, extraction, return_state=True), logger)
        if observe_failed:
            degraded.append("observe")

        # Etapa CRÍTICA: sin carga correcta no hay éxito. Decisión explícita sobre su estado.
        load_state = load_task(transformation.rows, window, run_id, return_state=True)
        if not load_state.is_completed():
            load_error = load_state.result(raise_on_failure=False)
            if not isinstance(load_error, BaseException):
                load_error = RuntimeError(f"load-weekly-kpis terminó en estado {load_state.name}")
            raise fail(load_error) from load_error
        loaded: LoadResult = load_state.result()
    except PipelineRunFailed:
        raise
    except Exception as error:  # extract o transform fallidos (tras sus reintentos) o checkpoint imposible
        raise fail(error) from error

    stats: dict[str, Any] = {
        "weeks": [week.isoformat() for week in window.weeks],
        "events_read": transformation.events_read,
        "events_rejected": transformation.rejected,
        "warnings": observations.get("warnings", []),
        "source_health": observations.get("source_health"),
        "capture_coverage": observations.get("capture_coverage"),
        "changes": loaded.changes,
        "prefect": {
            "flow_run_name": current_flow_run.name,
            "transform_cache": cache,
            "source_fingerprint": extraction.fingerprint,
            "code_version": CODE_VERSION,
        },
    }

    # Etapa OPCIONAL: snapshot de evaluación. Va antes de cerrar el registro para que el registro diga si se guardó.
    snapshot_state = eval_snapshot_task(
        run_id,
        {
            "pipeline": PIPELINE_NAME,
            "environment": environment,
            "week_from": window.first,
            "week_to": window.last,
            **stats,
            "rows": transformation.rows,
        },
        return_state=True,
    )
    if snapshot_state.is_completed():
        stats["eval_snapshot"] = snapshot_state.result()
    else:
        logger.warning("write-eval-snapshot no disponible (%s): el reporte ya está cargado", snapshot_state.name)
        degraded.append("eval_snapshot")

    outcome: Outcome = "partial" if degraded else "succeeded"
    stats.update(outcome=outcome, degraded=degraded)
    close_run(
        run_id,
        {
            "status": "succeeded",
            "phase": "loaded",
            "finished_at": datetime.now(UTC),
            "duration_ms": elapsed_ms(),
            "events_read": transformation.total_read,
            "events_rejected": transformation.total_rejected,
            "rows_upserted": loaded.rows_upserted,
            "rows_deleted": loaded.rows_deleted,
            "stats": stats,
        },
    )
    logger.info(
        "Ejecución %s %s: %d eventos leídos, %d rechazados, %d filas escritas, %d eliminadas, caché %s",
        run_id,
        outcome,
        transformation.total_read,
        transformation.total_rejected,
        loaded.rows_upserted,
        loaded.rows_deleted,
        cache,
    )
    return runs.get_run(run_id) or {}


@dataclass
class Computation:
    """Resultado sin escrituras (`--dry-run`): filas que se cargarían y señales del origen."""

    window: WeekWindow
    environment: str
    rows: list[dict]
    events_read: dict[str, int]
    rejected: dict[str, dict[str, int]]
    observations: dict[str, Any] = field(default_factory=dict)

    @property
    def total_read(self) -> int:
        return sum(self.events_read.values())

    @property
    def total_rejected(self) -> int:
        return sum(sum(by_reason.values()) for by_reason in self.rejected.values())

    def stats(self) -> dict[str, Any]:
        return {
            "weeks": [week.isoformat() for week in self.window.weeks],
            "events_read": self.events_read,
            "events_rejected": self.rejected,
            "warnings": self.observations.get("warnings", []),
            "source_health": self.observations.get("source_health"),
            "capture_coverage": self.observations.get("capture_coverage"),
        }


@flow(name="weekly-warehouse-client-performance-preview", persist_result=False)
def compute_weekly_performance(window: WeekWindow, environment: str) -> Computation:
    """extract → transform (+ observe opcional) sin escribir nada ni registrar la ejecución (`--dry-run`)."""
    extraction = extract_task(window, environment)
    transformation = transform_task(extraction, window.weeks)
    observations, _ = _observations(observe_task(window, extraction, return_state=True), get_run_logger())
    return Computation(
        window=window,
        environment=environment,
        rows=transformation.rows,
        events_read=transformation.events_read,
        rejected=transformation.rejected,
        observations=observations,
    )


# Una sola ejecución a la vez en el proceso (el índice único parcial de pipeline_runs lo garantiza entre procesos).
_run_lock = threading.Lock()


def run_weekly_performance(
    *,
    week_start: date | None = None,
    weeks: int = DEFAULT_WEEKS,
    trigger: Trigger = "cli",
    triggered_by: str | None = None,
    request_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Valida la ventana y ejecuta `weekly_performance_flow`. Lo usan la línea de comandos y la API.

    - `WindowError` (sin registrar nada ni crear un flow run) si los parámetros no son válidos.
    - `PipelineAlreadyRunning` si ya hay una ejecución en curso, en este proceso o en otro.
    - `ReportingStorageError` si ni siquiera se puede registrar la ejecución.
    - `PipelineRunFailed` si falla una etapa crítica.
    """
    window = resolve_window(week_start, weeks, now)
    if not _run_lock.acquire(blocking=False):
        raise PipelineAlreadyRunning("Ya hay una ejecución del pipeline semanal en curso.")
    try:
        return weekly_performance_flow(
            week_from=window.first,
            week_to=window.last,
            trigger=trigger,
            triggered_by=triggered_by,
            request_id=request_id,
        )
    finally:
        _run_lock.release()


# --- Línea de comandos -----------------------------------------------------------------------------------------------


def _database_label() -> str:
    """Qué base se va a usar, sin credenciales."""
    from sqlalchemy import make_url

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "SQLite local de la API (sin DATABASE_URL)"
    try:
        parsed = make_url(url)
    except Exception:
        return "DATABASE_URL (no interpretable)"
    return f"{parsed.get_backend_name()} en {parsed.host or 'local'} (DATABASE_URL)"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python data/pipelines/pipeline.py",
        description="Reporte Semanal de Desempeño por Almacén y Cliente (Prefect 3): recalcula semanas completas.",
    )
    parser.add_argument(
        "--week-start", type=date.fromisoformat, help="Semana más reciente a calcular (un lunes, YYYY-MM-DD)."
    )
    parser.add_argument(
        "--weeks", type=int, default=DEFAULT_WEEKS, help=f"Semanas hacia atrás (por defecto {DEFAULT_WEEKS})."
    )
    parser.add_argument("--dry-run", action="store_true", help="Calcula y muestra las filas sin escribir nada.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
    args = _parse_args(argv)
    print(f"Base de datos: {_database_label()} · entorno de eventos: {get_environment()}", file=sys.stderr)
    try:
        if args.dry_run:
            window = resolve_window(args.week_start, args.weeks)
            computation = compute_weekly_performance(window, get_environment())
            preview = {**computation.stats(), "rows": computation.rows}
            print(json.dumps(preview, default=str, indent=2, ensure_ascii=False))
            return 0
        run = run_weekly_performance(week_start=args.week_start, weeks=args.weeks, trigger="cli")
    except (WindowError, PipelineAlreadyRunning) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (PipelineRunFailed, ReportingStorageError) as error:
        print(f"La ejecución ha fallado: {error}", file=sys.stderr)
        return 1
    stats = run.get("stats") or {}
    outcome = stats.get("outcome", run["status"])
    print(
        f"Ejecución {run['id']} {outcome}: semanas {run['week_from']} → {run['week_to']}, "
        f"{run['events_read']} eventos leídos ({run['events_rejected']} rechazados), "
        f"{run['rows_upserted']} filas escritas, {run['rows_deleted']} eliminadas, {run['duration_ms']} ms, "
        f"caché de la transformación: {stats.get('prefect', {}).get('transform_cache', '-')}."
    )
    if stats.get("degraded"):
        print(f"Etapas opcionales con fallo: {', '.join(stats['degraded'])}.")
    if stats.get("warnings"):
        print(f"Avisos: {', '.join(stats['warnings'])}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
