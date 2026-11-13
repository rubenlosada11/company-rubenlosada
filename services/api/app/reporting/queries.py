"""Lecturas de la tabla del reporte para `GET /reporting/weekly-warehouse-client-performance`."""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.reporting.tables import KPI_COLUMNS, reporting_engine, storage_error, weekly_performance

ENTRY_COLUMNS = ("warehouse", "client_id", *KPI_COLUMNS)


def latest_week() -> date | None:
    """`week_start` más reciente con filas calculadas, o `None` si la tabla está vacía."""
    try:
        with reporting_engine().connect() as connection:
            return connection.execute(select(func.max(weekly_performance.c.week_start))).scalar()
    except SQLAlchemyError as error:
        raise storage_error(error) from None


def week_rows(week_start: date) -> list[dict[str, Any]]:
    """Filas de la semana, ordenadas por almacén y cliente, con `computed_at`."""
    table = weekly_performance
    statement = (
        select(*(table.c[name] for name in (*ENTRY_COLUMNS, "computed_at")))
        .where(table.c.week_start == week_start)
        .order_by(table.c.warehouse, table.c.client_id)
    )
    try:
        with reporting_engine().connect() as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]
    except SQLAlchemyError as error:
        raise storage_error(error) from None
