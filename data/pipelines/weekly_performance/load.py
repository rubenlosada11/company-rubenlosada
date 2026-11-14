"""load: escritura idempotente en `reporting.weekly_warehouse_client_performance` (PIPELINE_DESIGN §8).

Todo en **una transacción** (o se escriben todas las semanas de la ventana o ninguna):

1. **Reconciliación**: se borran las filas de las semanas de la ventana cuya combinación `(warehouse, client_id)` ya
   no está en el resultado. Con un origen de solo inserción no debería ocurrir; cubre una purga de retención futura y
   deja cada semana recalculada como copia exacta de su origen.
2. **Upsert** sobre `unique (warehouse, client_id, week_start)`: `INSERT … ON CONFLICT (…) DO UPDATE` de los KPIs,
   `computed_at` y `run_id`. Una fila existente conserva su `id`.

Repetir la carga con las mismas filas deja la tabla igual (salvo `computed_at` y `run_id`). Solo escribe en
`reporting`. Como es una única transacción idempotente, la task `load-weekly-kpis` puede reintentarla sin riesgo ante
un fallo transitorio: un intento fallido no deja nada escrito y el siguiente parte de la misma tabla.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.reporting.tables import KEY_COLUMNS, KPI_COLUMNS, reporting_engine, storage_error, weekly_performance
from app.reporting.weeks import WeekWindow

logger = logging.getLogger("trackflow.reporting.load")


CHANGE_KINDS = ("inserted", "updated", "unchanged", "deleted")


@dataclass(frozen=True)
class LoadResult:
    rows_upserted: int
    rows_deleted: int
    # Por semana (`YYYY-MM-DD`): filas insertadas, actualizadas, sin cambios y eliminadas. Es el rastro de qué semanas
    # ya publicadas ha modificado esta ejecución (p. ej. por eventos tardíos).
    changes: dict[str, dict[str, int]] = field(default_factory=dict)


def _upsert_statement(dialect: str, rows: list[dict]):
    insert = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}.get(dialect)
    if insert is None:
        raise NotImplementedError(f"Base de datos no soportada por el pipeline: {dialect}")
    statement = insert(weekly_performance).values(rows)
    return statement.on_conflict_do_update(
        index_elements=list(KEY_COLUMNS),
        set_={column: statement.excluded[column] for column in (*KPI_COLUMNS, "computed_at", "run_id")},
    )


def _changes(previous: dict[tuple, tuple], rows: list[dict], deleted: list[tuple], window: WeekWindow) -> dict:
    changes = {week.isoformat(): dict.fromkeys(CHANGE_KINDS, 0) for week in window.weeks}
    for row in rows:
        key = tuple(row[column] for column in KEY_COLUMNS)
        kpis = tuple(row[column] for column in KPI_COLUMNS)
        kind = "inserted" if key not in previous else ("unchanged" if previous[key] == kpis else "updated")
        changes[row["week_start"].isoformat()][kind] += 1
    for key in deleted:
        changes[key[2].isoformat()]["deleted"] += 1
    return changes


def load_rows(
    rows: list[dict], window: WeekWindow, computed_at: datetime, run_id: uuid.UUID | None = None
) -> LoadResult:
    """Deja las semanas de `window` exactamente con `rows` (filas de `aggregate`). `ReportingStorageError` si falla.

    Cada fila guarda el `run_id` de la ejecución que la escribió. Antes de escribir se leen las filas actuales de la
    ventana (en la misma transacción) para contar qué cambia en cada semana.
    """
    table = weekly_performance
    key_columns = [table.c[column] for column in KEY_COLUMNS]
    keys = [tuple(row[column] for column in KEY_COLUMNS) for row in rows]
    current = select(*key_columns, *(table.c[column] for column in KPI_COLUMNS)).where(
        table.c.week_start.in_(window.weeks)
    )
    stale = delete(table).where(table.c.week_start.in_(window.weeks)).returning(*key_columns)
    if keys:
        stale = stale.where(tuple_(*key_columns).not_in(keys))
    try:
        engine = reporting_engine()
        with engine.begin() as connection:
            previous = {tuple(row[:3]): tuple(row[3:]) for row in connection.execute(current)}
            deleted = [tuple(row) for row in connection.execute(stale)]
            if rows:
                values = [{"id": uuid.uuid4(), **row, "computed_at": computed_at, "run_id": run_id} for row in rows]
                connection.execute(_upsert_statement(connection.dialect.name, values))
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    changes = _changes(previous, rows, deleted, window)
    logger.info(
        "Pipeline semanal · load: %d filas escritas, %d eliminadas; cambios %s", len(rows), len(deleted), changes
    )
    return LoadResult(rows_upserted=len(rows), rows_deleted=len(deleted), changes=changes)
