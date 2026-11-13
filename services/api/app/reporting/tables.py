"""Tablas del esquema `reporting` y motor para usarlas.

- **PostgreSQL / Supabase** (`DATABASE_URL`): las crea la migración
  `migrations/20261113120000_reporting_weekly_performance.sql` (esquema, restricciones, índices, RLS y privilegios). La
  API nunca las crea ni las altera: si faltan, el pipeline falla y el endpoint responde 503.
- **SQLite** (sin `DATABASE_URL`, desarrollo local y tests): SQLite no tiene esquemas, así que el motor traduce
  `reporting` a la base principal (`schema_translate_map`) y crea tablas equivalentes al primer uso.

Las tablas se declaran en un `MetaData` propio (como `telemetry_events`): el `create_all` del inventario no las crea en
PostgreSQL sin la seguridad de la migración.
"""

import weakref

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Engine,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine

SCHEMA = "reporting"
MIGRATION_FILE = "migrations/20261113120000_reporting_weekly_performance.sql"

metadata = MetaData(schema=SCHEMA)

# Columnas del BRIEFING (§5) más `run_id` (trazabilidad). `discrepancy_rate`: `numeric` en la base, `float` en Python.
weekly_performance = Table(
    "weekly_warehouse_client_performance",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("warehouse", Text, nullable=False),
    Column("client_id", Text, nullable=False),
    Column("week_start", Date, nullable=False),
    Column("inbound_units_count", Integer, nullable=False, default=0),
    Column("outbound_orders_count", Integer, nullable=False, default=0),
    Column("stockout_events_count", Integer, nullable=False, default=0),
    Column("discrepancy_events_count", Integer, nullable=False, default=0),
    Column("discrepancy_rate", Numeric(asdecimal=False), nullable=False, default=0),
    Column("computed_at", DateTime(timezone=True), nullable=False),
    Column("run_id", Uuid, nullable=True),
    UniqueConstraint("warehouse", "client_id", "week_start"),
)

KEY_COLUMNS = ("warehouse", "client_id", "week_start")
KPI_COLUMNS = (
    "inbound_units_count",
    "outbound_orders_count",
    "stockout_events_count",
    "discrepancy_events_count",
    "discrepancy_rate",
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("pipeline", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("trigger", Text, nullable=False),
    Column("triggered_by", Text, nullable=True),
    Column("request_id", Uuid, nullable=True),
    Column("environment", Text, nullable=False),
    Column("week_from", Date, nullable=False),
    Column("week_to", Date, nullable=False),
    Column("phase", Text, nullable=False, default="started"),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("events_read", Integer, nullable=True),
    Column("events_rejected", Integer, nullable=True),
    Column("rows_upserted", Integer, nullable=True),
    Column("rows_deleted", Integer, nullable=True),
    Column("stats", JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    Column("error", Text, nullable=True),
    # Candado entre procesos: como mucho una ejecución `running` por pipeline (índice único parcial).
    Index(
        "pipeline_runs_one_running_idx",
        "pipeline",
        unique=True,
        sqlite_where=text("status = 'running'"),
        postgresql_where=text("status = 'running'"),
    ),
)

PHASES = ("started", "extracted", "validated", "aggregated", "loaded")


class ReportingStorageError(Exception):
    """No se ha podido leer o escribir en el esquema `reporting` (base caída, migración sin aplicar, permisos…).

    El mensaje solo dice el tipo de error, nunca la cadena de conexión ni los datos.
    """


def storage_error(error: SQLAlchemyError) -> ReportingStorageError:
    cause = getattr(error, "orig", None) or error
    sqlstate = getattr(cause, "sqlstate", None)
    return ReportingStorageError(type(cause).__name__ + (f" (SQLSTATE {sqlstate})" if sqlstate else ""))


# Motores SQLite en los que ya se han creado las tablas (los tests usan una base distinta en cada test).
_sqlite_ready: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def reporting_engine() -> Engine:
    """Motor de la base de `DATABASE_URL` para las tablas de `reporting`.

    En SQLite devuelve el mismo motor con `reporting` traducido a la base principal y crea las tablas si faltan.
    """
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return engine
    translated = engine.execution_options(schema_translate_map={SCHEMA: None})
    if engine not in _sqlite_ready:
        metadata.create_all(translated)
        _sqlite_ready.add(engine)
    return translated
