"""Subflow 4 · load: escritura idempotente en `reporting.weekly_warehouse_client_performance` (PIPELINE_DESIGN §8).

Todo en **una transacción** (o se escriben todas las semanas de la ventana o ninguna):

1. **Reconciliación**: se borran las filas de las semanas de la ventana cuya combinación `(warehouse, client_id)` ya
   no está en el resultado. Con un origen de solo inserción no debería ocurrir; cubre una purga de retención futura y
   deja cada semana recalculada como copia exacta de su origen.
2. **Upsert** sobre `unique (warehouse, client_id, week_start)`: `INSERT … ON CONFLICT (…) DO UPDATE` de los KPIs y
   de `computed_at`. Una fila existente conserva su `id`.

Repetir la carga con las mismas filas deja la tabla igual (salvo `computed_at`). Solo escribe en `reporting`.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.reporting.tables import KEY_COLUMNS, KPI_COLUMNS, reporting_engine, storage_error, weekly_performance
from app.reporting.weeks import WeekWindow

logger = logging.getLogger("trackflow.reporting.load")


@dataclass(frozen=True)
class LoadResult:
    rows_upserted: int
    rows_deleted: int


def _upsert_statement(dialect: str, rows: list[dict]):
    insert = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}.get(dialect)
    if insert is None:
        raise NotImplementedError(f"Base de datos no soportada por el pipeline: {dialect}")
    statement = insert(weekly_performance).values(rows)
    return statement.on_conflict_do_update(
        index_elements=list(KEY_COLUMNS),
        set_={column: statement.excluded[column] for column in (*KPI_COLUMNS, "computed_at")},
    )


def load_rows(rows: list[dict], window: WeekWindow, computed_at: datetime) -> LoadResult:
    """Deja las semanas de `window` exactamente con `rows` (filas de `aggregate`). `ReportingStorageError` si falla."""
    table = weekly_performance
    keys = [tuple(row[column] for column in KEY_COLUMNS) for row in rows]
    stale = delete(table).where(table.c.week_start.in_(window.weeks)).returning(table.c.id)
    if keys:
        stale = stale.where(tuple_(*(table.c[column] for column in KEY_COLUMNS)).not_in(keys))
    try:
        engine = reporting_engine()
        with engine.begin() as connection:
            deleted = len(connection.execute(stale).all())
            if rows:
                values = [{"id": uuid.uuid4(), **row, "computed_at": computed_at} for row in rows]
                connection.execute(_upsert_statement(connection.dialect.name, values))
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    logger.info("Pipeline semanal · load: %d filas escritas, %d eliminadas", len(rows), deleted)
    return LoadResult(rows_upserted=len(rows), rows_deleted=deleted)
