"""extract: eventos de origen de `telemetry_events`, **solo lectura** (PIPELINE_DESIGN.md §6.1).

Una única consulta con todos los filtros en SQL —los cuatro `event_type`, el entorno y la ventana `[inicio, fin)`—,
servida por los índices de `timestamp` y `event_type` de la migración de telemetría. Nunca se carga la tabla entera.

En PostgreSQL la consulta corre en una transacción de solo lectura (`postgresql_readonly` → `BEGIN READ ONLY`): la
base rechazaría cualquier escritura aunque el código la intentara. Este módulo no contiene ninguna sentencia que
escriba en `telemetry_events`.

Los errores de la base salen como `ReportingStorageError` con `transient=True` si merece la pena reintentar (conexión
caída, base reiniciando…): la task `extract-telemetry-events` de `pipeline.py` reintenta solo esos.
"""

import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.reporting.tables import storage_error
from app.reporting.weeks import WeekWindow
from app.telemetry.storage import telemetry_engine, telemetry_events
from data.process.weekly_performance.events import COLUMNS, SOURCE_EVENT_TYPES

logger = logging.getLogger("trackflow.reporting.extract")


def extract_events(window: WeekWindow, environment: str) -> pd.DataFrame:
    """Eventos de los cuatro tipos del entorno `environment` dentro de la ventana, en orden cronológico.

    DataFrame con las columnas `COLUMNS` (también si no hay filas). `ReportingStorageError` si no se puede leer.
    """
    table = telemetry_events
    statement = (
        select(*(table.c[name] for name in COLUMNS))
        .where(
            table.c.event_type.in_(SOURCE_EVENT_TYPES),
            table.c.environment == environment,
            table.c.timestamp >= window.start,
            table.c.timestamp < window.end,
        )
        .order_by(table.c.timestamp, table.c.id)
    )
    try:
        with telemetry_engine().connect() as connection:
            connection = connection.execution_options(postgresql_readonly=True)
            with connection.begin():
                rows = connection.execute(statement).all()
    except SQLAlchemyError as error:
        raise storage_error(error) from None
    logger.info(
        "Pipeline semanal · extract: %d eventos (%s) de [%s, %s)",
        len(rows),
        environment,
        window.start.date().isoformat(),
        window.end.date().isoformat(),
    )
    return pd.DataFrame(rows, columns=COLUMNS)
