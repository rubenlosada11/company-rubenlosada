"""Almacenamiento de la telemetría: tabla `telemetry_events` en la base de `DATABASE_URL`.

- **PostgreSQL / Supabase** (`DATABASE_URL`): la tabla la crea la migración
  `migrations/20261110120000_telemetry_events.sql` (índices, RLS, privilegios y triggers de solo inserción). La API
  nunca la crea ni la altera: si falta, la inserción falla y el receptor responde 503.
- **SQLite** (sin `DATABASE_URL`, desarrollo local y tests): la API crea una tabla equivalente al primer uso, sin
  índices ni triggers.

La tabla se declara en un `MetaData` propio, no en `SQLModel.metadata`: así el `create_all` del inventario
(`app/database.py`) no la crea en PostgreSQL sin la seguridad de la migración.

Solo se inserta: no hay funciones de actualización ni de borrado. Cada lote es **una sola sentencia**
`INSERT … VALUES (…), (…) ON CONFLICT (id) DO NOTHING` dentro de una transacción: se guarda entero o no se guarda nada.
`ON CONFLICT` hace que reenviar un evento (mismo `eventId`, p. ej. un reintento del navegador o un evento determinista
reconstruido, §18.3 del plan) no lo duplique ni haga fallar el lote.
"""

import uuid
import weakref
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Engine, MetaData, Table, Text, Uuid, insert
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.telemetry import contract
from app.telemetry.models import TelemetryEvent

TABLE_NAME = "telemetry_events"
MIGRATION_FILE = "migrations/20261110120000_telemetry_events.sql"

metadata = MetaData()

# Mismas columnas y en el mismo orden que la migración. `tags` es JSONB en PostgreSQL y JSON en SQLite.
telemetry_events = Table(
    TABLE_NAME,
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("event_type", Text, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("service", Text, nullable=False),
    Column("tags", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("session_id", Uuid, nullable=True),
    Column("user_id", Text, nullable=True),
    Column("request_id", Uuid, nullable=True),
    Column("schema_version", Text, nullable=False),
    Column("environment", Text, nullable=False),
)


class TelemetryStorageError(Exception):
    """No se ha podido guardar un lote (base caída, tabla sin crear, permisos…). No se ha guardado ningún evento.

    El mensaje solo dice el tipo de error, nunca los valores del lote ni la cadena de conexión.
    """


def to_row(event: TelemetryEvent) -> dict[str, Any]:
    """Fila de `telemetry_events` para un evento **ya validado** con `TelemetryEvent`.

    `tags` copia solo las claves de la allowlist del `event_type` (el modelo ya rechaza las demás: esta copia campo a
    campo es una segunda barrera, §11 del plan). `timestamp` pasa de texto ISO 8601 con `Z` a fecha con zona UTC.
    """
    allowlist = contract.allowed_properties(event.event_type)
    return {
        "id": uuid.UUID(event.event_id),
        "event_type": event.event_type,
        "timestamp": datetime.fromisoformat(event.timestamp),
        "service": event.source,
        "tags": {key: event.properties[key] for key in allowlist if key in event.properties},
        "session_id": uuid.UUID(event.session_id) if event.session_id else None,
        "user_id": event.user_id,
        "request_id": uuid.UUID(event.request_id) if event.request_id else None,
        "schema_version": event.schema_version,
        "environment": event.environment,
    }


# Motores SQLite en los que ya se ha creado la tabla (los tests usan una base distinta en cada test).
_sqlite_ready: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def _engine() -> Engine:
    engine = get_engine()
    if engine.dialect.name == "sqlite" and engine not in _sqlite_ready:
        metadata.create_all(engine)
        _sqlite_ready.add(engine)
    return engine


def _insert_statement(engine: Engine, rows: list[dict[str, Any]]):
    """`INSERT … VALUES (…), (…) ON CONFLICT (id) DO NOTHING RETURNING id`: devuelve solo los ids insertados.

    Las filas nuevas se cuentan con `RETURNING` y no con `rowcount`, que no todos los drivers informan (con psycopg
    detrás del pooler de Supabase llega como -1).
    """
    dialect = engine.dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(telemetry_events).values(rows).on_conflict_do_nothing(index_elements=["id"])
    elif dialect == "sqlite":
        statement = sqlite_insert(telemetry_events).values(rows).on_conflict_do_nothing(index_elements=["id"])
    else:
        statement = insert(telemetry_events).values(rows)
    return statement.returning(telemetry_events.c.id)


def insert_events(events: Sequence[TelemetryEvent]) -> int:
    """Guarda un lote de eventos validados con **un único INSERT** en una transacción. Devuelve las filas nuevas.

    Un evento cuyo `eventId` ya estaba guardado no se vuelve a insertar (no cuenta como fila nueva). Sin eventos no se
    toca la base. Si algo falla lanza `TelemetryStorageError` y no queda ninguna fila del lote.
    """
    if not events:
        return 0
    rows = [to_row(event) for event in events]
    try:
        engine = _engine()
        with engine.begin() as connection:
            inserted = len(connection.execute(_insert_statement(engine, rows)).all())
    except SQLAlchemyError as error:
        cause = getattr(error, "orig", None) or error
        sqlstate = getattr(cause, "sqlstate", None)
        detail = type(cause).__name__ + (f" (SQLSTATE {sqlstate})" if sqlstate else "")
        raise TelemetryStorageError(detail) from None
    return inserted
