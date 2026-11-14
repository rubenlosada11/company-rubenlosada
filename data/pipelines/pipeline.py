"""Pipeline de Desempeño de Negocio Resiliente — Reporte Semanal de Desempeño por Almacén y Cliente (Prefect 3).

Punto de entrada y definición de los flows. Diseño: `data/pipelines/PIPELINE_DESIGN.md` (§18, implementación con
Prefect; §19, subflows del Hito 6). El flow principal **coordina** subflows (cada uno, un `@flow` con su propio
estado en Prefect) y registra la ejecución; no lee, calcula ni escribe datos por sí mismo:

    @flow weekly-warehouse-client-performance                     (principal)
      register-run                                                task: fila `running` en reporting.pipeline_runs
      ├─ @flow extract-weekly-inventory-events                    SUBFLOW 1 · extracción
      │     extract-telemetry-events                              telemetry_events (solo lectura), reintentos
      ├─ @flow compute-weekly-warehouse-client-kpis               SUBFLOW 2 · transformación (una task por KPI)
      │     prepare-weekly-events                                 validate + semana ISO; CACHÉ (cache_key_fn)
      │     compute-inbound-volume · compute-outbound-throughput · compute-stockout-frequency
      │     count-inventory-discrepancies → compute-discrepancy-rate
      │     assemble-weekly-report-rows                           filas + controles de coherencia
      ├─ @flow observe-source-health                              OPCIONAL (return_state=True): si falla, «parcial»
      ├─ @flow load-weekly-warehouse-client-performance           SUBFLOW 3 · carga, CRÍTICO (return_state=True)
      │     load-weekly-kpis                                      upsert + reconciliación, una transacción
      ├─ @flow export-eval-snapshot                               OPCIONAL (return_state=True): JSON en data/eval/
      close-run                                                   task: cierra el registro
    → reporting.weekly_warehouse_client_performance  +  reporting.pipeline_runs

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
from pydantic import BaseModel, ConfigDict, model_serializer  # noqa: E402

from app.reporting import runs  # noqa: E402
from app.reporting.tables import ReportingStorageError  # noqa: E402
from app.reporting.weeks import DEFAULT_WEEKS, WeekWindow, WindowError, is_monday, resolve_window  # noqa: E402
from app.telemetry.config import get_environment  # noqa: E402
from data.pipelines.weekly_performance.evaluation import write_snapshot  # noqa: E402
from data.pipelines.weekly_performance.extract import extract_events  # noqa: E402
from data.pipelines.weekly_performance.load import LoadResult, load_rows  # noqa: E402
from data.pipelines.weekly_performance.observe import UNAVAILABLE, observe  # noqa: E402
from data.process.weekly_performance.events import COLUMNS  # noqa: E402
from data.process.weekly_performance.kpis import (  # noqa: E402
    build_rows,
    discrepancy_count,
    discrepancy_rate,
    inbound_volume,
    outbound_throughput,
    stockout_frequency,
)
from data.process.weekly_performance.transform import (  # noqa: E402
    CODE_VERSION,
    PreparedEvents,
    check_consistency,
    fingerprint_events,
    prepare_events,
)
from data.process.weekly_performance.validate import SourceSchemaError  # noqa: E402

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
# Desde el Hito 6 se cachea `prepare-weekly-events` (validate + semana ISO), la etapa costosa de la transformación
# (reglas fila a fila); las tasks de KPI son agregaciones vectorizadas de milisegundos y se recalculan siempre.
# La clave identifica TODO lo que determina el resultado de la preparación, y nada más:
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


# --- Datos que viajan entre subflows ---------------------------------------------------------------------------------
# Prefect guarda en su base los parámetros de cada flow run (lo que se ve en la interfaz) convirtiéndolos a JSON con el
# `jsonable_encoder` de FastAPI, y su servidor rechaza los que pasan de 512 KB. Un DataFrame de eventos o las filas de
# un backfill superan ese límite enseguida (3.000 eventos ≈ 700 KB), y además no deben quedar copiados en Prefect.
# Por eso lo que pasa de un subflow a otro son modelos Pydantic cuyo serializador devuelve un RESUMEN (recuentos, entorno
# y huella): los datos viajan en memoria y Prefect registra una descripción legible de lo que recibió cada subflow.

_DATA_MODEL = ConfigDict(arbitrary_types_allowed=True, frozen=True)


class Extraction(BaseModel):
    """Salida del subflow de extracción: eventos crudos, entorno y huella de su contenido (entrada de la caché)."""

    model_config = _DATA_MODEL

    events: pd.DataFrame
    environment: str
    fingerprint: str

    @property
    def count(self) -> int:
        return len(self.events)

    @model_serializer
    def _summary(self) -> dict[str, Any]:
        """Lo que Prefect guarda como parámetro de un subflow: el resumen, nunca los eventos."""
        return {"events": self.count, "environment": self.environment, "fingerprint": self.fingerprint}


class WeeklyKpis(BaseModel):
    """Salida del subflow de transformación: filas del reporte, recuentos de calidad y uso de la caché.

    Mismos campos que `Transformation` (data/process) más `transform_cache`. Es la entrada del subflow de carga.
    """

    model_config = _DATA_MODEL

    rows: list[dict]
    events_read: dict[str, int]
    rejected: dict[str, dict[str, int]]
    transform_cache: Literal["hit", "miss"] = "miss"

    @property
    def total_read(self) -> int:
        return sum(self.events_read.values())

    @property
    def total_rejected(self) -> int:
        return sum(sum(by_reason.values()) for by_reason in self.rejected.values())

    @model_serializer
    def _summary(self) -> dict[str, Any]:
        """Lo que Prefect guarda como parámetro de un subflow: recuentos, nunca las filas."""
        return {
            "rows": len(self.rows),
            "events_read": self.total_read,
            "events_rejected": self.total_rejected,
            "transform_cache": self.transform_cache,
        }


def transform_cache_key(context, parameters: dict[str, Any]) -> str:
    """`cache_key_fn` de `prepare-weekly-events`: ver el comentario de arriba."""
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
    name="prepare-weekly-events",
    cache_key_fn=transform_cache_key,
    cache_expiration=TRANSFORM_CACHE_EXPIRATION,
)
def prepare_task(extraction: Extraction, weeks: list[date]) -> PreparedEvents:
    """validate (rechaza y cuenta los eventos mal formados) → semana ISO → ventana. Pura: se puede cachear."""
    return prepare_events(extraction.events, weeks)


# Tasks de KPI: una por indicador del BRIEFING (§2). Cada una envuelve una función pura de
# data/process/weekly_performance/kpis.py, sin E/S ni logger de Prefect, para que se pueda probar llamando a `.fn`.


@task(name="compute-inbound-volume", cache_policy=NO_CACHE)
def inbound_volume_task(events: pd.DataFrame) -> pd.Series:
    """KPI «Volumen de entrada»: unidades recibidas por almacén, cliente y semana."""
    return inbound_volume(events)


@task(name="compute-outbound-throughput", cache_policy=NO_CACHE)
def outbound_throughput_task(events: pd.DataFrame) -> pd.Series:
    """KPI «Throughput de salida»: pedidos despachados por almacén, cliente y semana."""
    return outbound_throughput(events)


@task(name="compute-stockout-frequency", cache_policy=NO_CACHE)
def stockout_frequency_task(events: pd.DataFrame) -> pd.Series:
    """KPI «Frecuencia de quiebre de stock»: veces bajo el mínimo por almacén, cliente y semana."""
    return stockout_frequency(events)


@task(name="count-inventory-discrepancies", cache_policy=NO_CACHE)
def discrepancy_count_task(events: pd.DataFrame) -> pd.Series:
    """Conteo de apoyo de la «Tasa de discrepancia»: discrepancias detectadas por almacén, cliente y semana."""
    return discrepancy_count(events)


@task(name="compute-discrepancy-rate", cache_policy=NO_CACHE)
def discrepancy_rate_task(discrepancies: pd.Series, outbound_orders: pd.Series) -> pd.Series:
    """KPI «Tasa de discrepancia»: discrepancias / pedidos (4 decimales; 0 sin pedidos)."""
    return discrepancy_rate(discrepancies, outbound_orders)


@task(name="assemble-weekly-report-rows", cache_policy=NO_CACHE)
def assemble_rows_task(
    prepared: PreparedEvents,
    weeks: list[date],
    inbound_units: pd.Series,
    outbound_orders: pd.Series,
    stockouts: pd.Series,
    discrepancies: pd.Series,
    rates: pd.Series,
) -> list[dict]:
    """Filas de la tabla de destino + controles de coherencia (`InconsistentResultError` si algo no cuadra)."""
    rows = build_rows(inbound_units, outbound_orders, stockouts, discrepancies, rates)
    check_consistency(rows, prepared.events, weeks)
    return rows


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
    """Decisión sobre el subflow opcional `observe-source-health`: sus señales si terminó bien; si no, aviso y
    `degraded`."""
    if state.is_completed():
        return state.result(), False
    logger.warning("observe-source-health no disponible (%s): se continúa sin señales del origen", state.name)
    return {"warnings": [UNAVAILABLE]}, True


def _week_window(week_from: date, week_to: date) -> WeekWindow:
    """Ventana `[week_from, week_to]` de un subflow. `ValueError` si no son lunes o están al revés.

    `run_weekly_performance` ya valida la ventana antes de crear el flow run; esta comprobación protege a los subflows
    cuando se ejecutan por separado (p. ej. desde un notebook o los tests).
    """
    if not (is_monday(week_from) and is_monday(week_to)):
        raise ValueError("week_from y week_to deben ser lunes (inicio de la semana ISO).")
    if week_from > week_to:
        raise ValueError("week_from no puede ser posterior a week_to.")
    return WeekWindow(first=week_from, last=week_to)


# --- Subflows (Hito 6) -----------------------------------------------------------------------------------------------
# Cada etapa del ETL es un `@flow` con parámetros y resultado explícitos. Llamado desde otro flow, Prefect lo registra
# como **subflow** (un flow run hijo, enlazado al principal, con su propio estado); llamado directamente, se ejecuta
# solo. Ninguno depende de variables globales con estado: todo lo que necesitan llega por parámetros.


@flow(name="extract-weekly-inventory-events", persist_result=False)
def extract_weekly_inventory_events(week_from: date, week_to: date, environment: str) -> Extraction:
    """SUBFLOW 1 · extracción. Eventos de inventario (los 4 `event_type` del BRIEFING) del entorno y las semanas
    `[week_from, week_to]`, leídos de `telemetry_events` en solo lectura, con la huella de su contenido.

    Errores: `ValueError` (ventana no válida), `ReportingStorageError` (la base no responde tras los reintentos de
    `extract-telemetry-events`) o `SourceSchemaError` (la extracción no trae las columnas del contrato).
    """
    window = _week_window(week_from, week_to)
    extraction = extract_task(window, environment)
    missing = [column for column in COLUMNS if column not in extraction.events.columns]
    if missing:
        raise SourceSchemaError(f"Faltan columnas en la extracción: {', '.join(missing)}")
    return extraction


@flow(name="compute-weekly-warehouse-client-kpis", persist_result=False)
def compute_weekly_kpis(extraction: Extraction, weeks: list[date]) -> WeeklyKpis:
    """SUBFLOW 2 · transformación. Los cuatro KPIs por almacén, cliente y semana, una task por KPI.

    prepare-weekly-events (cacheada) → volumen de entrada, throughput de salida, quiebres de stock y discrepancias →
    tasa de discrepancia → filas + controles de coherencia. Independiente de la base: solo recibe la extracción.

    Errores: `SourceSchemaError`, `KpiInputError` o `InconsistentResultError` (no se carga nada).
    """
    logger = get_run_logger()
    prepared_state = prepare_task(extraction, weeks, return_state=True)
    prepared: PreparedEvents = prepared_state.result()  # si falló, relanza su excepción
    cache: Literal["hit", "miss"] = "hit" if prepared_state.name == "Cached" else "miss"
    if prepared.rejected:
        logger.warning("Eventos rechazados por calidad: %s", prepared.rejected)

    events = prepared.events
    inbound_units = inbound_volume_task(events)
    outbound_orders = outbound_throughput_task(events)
    stockouts = stockout_frequency_task(events)
    discrepancies = discrepancy_count_task(events)
    rates = discrepancy_rate_task(discrepancies, outbound_orders)
    rows = assemble_rows_task(prepared, weeks, inbound_units, outbound_orders, stockouts, discrepancies, rates)

    logger.info("%d filas del reporte calculadas (caché de la preparación: %s)", len(rows), cache)
    return WeeklyKpis(
        rows=rows, events_read=prepared.events_read, rejected=prepared.rejected, transform_cache=cache
    )


@flow(name="load-weekly-warehouse-client-performance", persist_result=False)
def load_weekly_performance(kpis: WeeklyKpis, week_from: date, week_to: date, run_id: uuid.UUID) -> LoadResult:
    """SUBFLOW 3 · carga. Upsert idempotente de las filas (`kpis.rows`) en
    `reporting.weekly_warehouse_client_performance` y reconciliación de las semanas `[week_from, week_to]`, en una
    transacción.

    Devuelve un `LoadResult` verificable (filas escritas y eliminadas, cambios por semana). Errores: `ValueError` si
    alguna fila es de otra semana (la reconciliación borraría datos de semanas que no se han recalculado) y
    `ReportingStorageError` si la base falla tras los reintentos (nada escrito).
    """
    window = _week_window(week_from, week_to)
    rows = kpis.rows
    outside = sorted({row["week_start"].isoformat() for row in rows if row["week_start"] not in window.weeks})
    if outside:
        raise ValueError(f"Filas fuera de la ventana de carga: {', '.join(outside)}")
    loaded = load_task(rows, window, run_id)
    get_run_logger().info("%d filas escritas, %d eliminadas", loaded.rows_upserted, loaded.rows_deleted)
    return loaded


@flow(name="observe-source-health", persist_result=False)
def observe_source_health(extraction: Extraction, week_from: date, week_to: date) -> dict[str, Any]:
    """Subflow OPCIONAL: salud del origen y cobertura frente al inventario (§17.2). Solo lectura."""
    return observe_task(_week_window(week_from, week_to), extraction)


@flow(name="export-eval-snapshot", persist_result=False)
def export_eval_snapshot(run_id: uuid.UUID, summary: dict[str, Any], kpis: WeeklyKpis) -> str:
    """Subflow OPCIONAL: snapshot JSON de la ejecución (`summary` + filas de `kpis`) en data/eval/ (§18.6).

    Devuelve su ruta. Las filas llegan dentro de `kpis` (no como parámetro suelto) para no copiarlas en Prefect.
    """
    return eval_snapshot_task(run_id, {**summary, "rows": kpis.rows})


# --- Flow principal --------------------------------------------------------------------------------------------------


@flow(name="weekly-warehouse-client-performance", persist_result=False)
def weekly_performance_flow(
    week_from: date,
    week_to: date,
    trigger: Trigger = "cli",
    triggered_by: str | None = None,
    request_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """ETL completo de las semanas `[week_from, week_to]` (lunes, ya validadas) y registro de la ejecución.

    Coordina los subflows en secuencia (extracción → transformación → observación opcional → carga → snapshot
    opcional) y registra la ejecución; no contiene lógica de extracción, cálculo ni escritura. Devuelve el registro (`status = succeeded`; `stats.outcome` = `succeeded` o `partial`). Lanza
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
        # SUBFLOW 1 · extracción. Si falla (tras los reintentos de su task), su excepción llega aquí.
        extraction = extract_weekly_inventory_events(window.first, window.last, environment)
        runs.set_phase(run_id, "extracted")

        # SUBFLOW 2 · transformación: los cuatro KPIs, una task por KPI.
        transformation = compute_weekly_kpis(extraction, window.weeks)
        cache = transformation.transform_cache
        runs.set_phase(run_id, "aggregated")

        # Subflow OPCIONAL: su fallo no detiene el flujo; la ejecución sigue y se marcará como parcial.
        observe_state = observe_source_health(extraction, window.first, window.last, return_state=True)
        observations, observe_failed = _observations(observe_state, logger)
        if observe_failed:
            degraded.append("observe")

        # SUBFLOW 3 · carga, CRÍTICO: sin carga correcta no hay éxito. Decisión explícita sobre su estado.
        load_state = load_weekly_performance(transformation, window.first, window.last, run_id, return_state=True)
        if not load_state.is_completed():
            load_error = load_state.result(raise_on_failure=False)
            if not isinstance(load_error, BaseException):
                load_error = RuntimeError(f"load-weekly-warehouse-client-performance terminó en estado {load_state.name}")
            raise fail(load_error) from load_error
        loaded: LoadResult = load_state.result()
    except PipelineRunFailed:
        raise
    except Exception as error:  # extracción o transformación fallidas (tras sus reintentos) o checkpoint imposible
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

    # Subflow OPCIONAL: snapshot de evaluación. Va antes de cerrar el registro para que el registro diga si se guardó.
    snapshot_state = export_eval_snapshot(
        run_id,
        {
            "pipeline": PIPELINE_NAME,
            "environment": environment,
            "week_from": window.first,
            "week_to": window.last,
            **stats,
        },
        transformation,
        return_state=True,
    )
    if snapshot_state.is_completed():
        stats["eval_snapshot"] = snapshot_state.result()
    else:
        logger.warning("export-eval-snapshot no disponible (%s): el reporte ya está cargado", snapshot_state.name)
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
    """Subflows de extracción y transformación (+ observación opcional) sin escribir nada ni registrar la ejecución
    (`--dry-run`)."""
    extraction = extract_weekly_inventory_events(window.first, window.last, environment)
    transformation = compute_weekly_kpis(extraction, window.weeks)
    observe_state = observe_source_health(extraction, window.first, window.last, return_state=True)
    observations, _ = _observations(observe_state, get_run_logger())
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
