"""Registro de ejecuciones de los pipelines (`reporting.pipeline_runs`, PIPELINE_DESIGN.md §9).

Cada ejecución se registra **antes** de empezar (`running`) y se cierra al terminar (`succeeded` o `failed`), en
transacciones propias: una ejecución fallida también deja rastro, aunque su carga se haya deshecho. El registro es
genérico (columna `pipeline`) para que cualquier pipeline futuro use el mismo patrón y el mismo endpoint.

Una ejecución que sigue en `running` más de `ABANDON_AFTER` (el proceso cayó a mitad) se marca `failed` con el error
`abandoned` cuando empieza la siguiente del mismo pipeline.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.reporting.tables import pipeline_runs, reporting_engine, storage_error

ABANDON_AFTER = timedelta(minutes=30)
ABANDONED = "abandoned"


def start_run(
    *,
    pipeline: str,
    trigger: str,
    triggered_by: str | None,
    environment: str,
    week_from: date,
    week_to: date,
    started_at: datetime,
) -> uuid.UUID:
    """Registra una ejecución `running` y devuelve su id. Antes marca como abandonadas las que se quedaron colgadas."""
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
                    environment=environment,
                    week_from=week_from,
                    week_to=week_to,
                    started_at=started_at,
                )
            )
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
