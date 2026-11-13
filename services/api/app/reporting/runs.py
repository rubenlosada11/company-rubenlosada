"""Registro de ejecuciones de los pipelines (`reporting.pipeline_runs`, PIPELINE_DESIGN.md §9).

Cada ejecución se registra **antes** de empezar (`running`) y se cierra al terminar (`succeeded` o `failed`), en
transacciones propias: una ejecución fallida también deja rastro, aunque su carga se haya deshecho. El registro es
genérico (columna `pipeline`) para que cualquier pipeline futuro use el mismo patrón y el mismo endpoint.

Una ejecución que sigue en `running` más de `ABANDON_AFTER` (el proceso cayó a mitad) se marca `failed` con el error
`abandoned` cuando empieza la siguiente del mismo pipeline.

- **Candado entre procesos:** el índice único parcial `pipeline_runs_one_running_idx` admite como mucho una fila
  `running` por pipeline. Si el `cron` y un `POST` coinciden, el segundo choca al registrarse (`RunInProgress` → 409)
  y no llega a leer ni a escribir nada.
- **Checkpoint de fase** (`phase`): último subflow completado (`extracted`, `validated`, `aggregated`, `loaded`). Una
  ejecución fallida dice dónde murió; la siguiente no retoma desde ahí, recalcula la ventana entera (es barato y la
  carga es idempotente), así que no hay estados intermedios que reconciliar.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.reporting.tables import pipeline_runs, reporting_engine, storage_error

ABANDON_AFTER = timedelta(minutes=30)
ABANDONED = "abandoned"


class RunInProgress(Exception):
    """Ya hay una ejecución `running` de este pipeline (de este u otro proceso)."""


def start_run(
    *,
    pipeline: str,
    trigger: str,
    triggered_by: str | None,
    environment: str,
    week_from: date,
    week_to: date,
    started_at: datetime,
    request_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Registra una ejecución `running` y devuelve su id. Antes marca como abandonadas las que se quedaron colgadas.

    `RunInProgress` si otra ejecución del mismo pipeline sigue `running` (índice único parcial).
    """
    run_id = uuid.uuid4()
    table = pipeline_runs
    try:
        with reporting_engine().begin() as connection:
            connection.execute(
                update(table)
                .where(
                    table.c.pipeline == pipeline,
                    table.c.status == "running",
                    table.c.started_at < started_at - ABANDON_AFTER,
                )
                .values(status="failed", finished_at=started_at, error=ABANDONED)
            )
            connection.execute(
                table.insert().values(
                    id=run_id,
                    pipeline=pipeline,
                    status="running",
                    trigger=trigger,
                    triggered_by=triggered_by,
                    request_id=request_id,
                    environment=environment,
                    week_from=week_from,
                    week_to=week_to,
                    phase="started",
                    started_at=started_at,
                )
            )
    except IntegrityError:
        raise RunInProgress(pipeline) from None
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    return run_id


def finish_run(run_id: uuid.UUID, **values: Any) -> None:
    """Cierra la ejecución con su estado, tiempos, recuentos y error (columnas de `pipeline_runs`)."""
    try:
        with reporting_engine().begin() as connection:
            connection.execute(update(pipeline_runs).where(pipeline_runs.c.id == run_id).values(**values))
    except SQLAlchemyError as error:
        raise storage_error(error) from None


def set_phase(run_id: uuid.UUID, phase: str) -> None:
    """Checkpoint: último subflow completado."""
    finish_run(run_id, phase=phase)


def _as_dict(row) -> dict[str, Any] | None:
    return dict(row._mapping) if row is not None else None


def get_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    try:
        with reporting_engine().connect() as connection:
            row = connection.execute(select(pipeline_runs).where(pipeline_runs.c.id == run_id)).first()
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    return _as_dict(row)


def latest_run(pipeline: str) -> dict[str, Any] | None:
    """Última ejecución del pipeline por fecha de inicio (en cualquier estado), o `None` si nunca se ha ejecutado."""
    table = pipeline_runs
    statement = (
        select(table).where(table.c.pipeline == pipeline).order_by(table.c.started_at.desc(), table.c.id).limit(1)
    )
    try:
        with reporting_engine().connect() as connection:
            row = connection.execute(statement).first()
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    return _as_dict(row)


def _covering(pipeline: str, week: date | None = None):
    table = pipeline_runs
    statement = select(table).where(table.c.pipeline == pipeline, table.c.status == "succeeded")
    if week is not None:
        statement = statement.where(table.c.week_from <= week, table.c.week_to >= week)
    return statement


def latest_covered_week(pipeline: str) -> date | None:
    """Semana más reciente calculada por alguna ejecución correcta (tenga filas o no), o `None`."""
    statement = select(func.max(pipeline_runs.c.week_to)).where(
        pipeline_runs.c.pipeline == pipeline, pipeline_runs.c.status == "succeeded"
    )
    try:
        with reporting_engine().connect() as connection:
            return connection.execute(statement).scalar()
    except SQLAlchemyError as error:
        raise storage_error(error) from None


def latest_covering_run(pipeline: str, week: date) -> dict[str, Any] | None:
    """Última ejecución correcta cuya ventana incluye `week`: separa «sin actividad» de «sin calcular»."""
    statement = _covering(pipeline, week).order_by(pipeline_runs.c.finished_at.desc()).limit(1)
    try:
        with reporting_engine().connect() as connection:
            row = connection.execute(statement).first()
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    return _as_dict(row)
