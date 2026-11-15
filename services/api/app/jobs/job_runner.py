"""Job runner: registro y máquina de estados de las ejecuciones en segundo plano (`job_runs`, DEV-53).

Solo **persistencia**: crea, consulta y cambia de estado las ejecuciones. Qué hace cada job (exportar, lanzar el
pipeline…) vive en su script (`scripts/nightly_export.py`). La API no importa este módulo.

Máquina de estados (docs/telemetry/nightly-export.md §3)::

    pending ──► processing ──► completed
       │             │
       └─────────────┴──────► failed

`pending → failed` solo ocurre si la ejecución falla o se abandona **antes** de empezar el trabajo: sin esa salida, un
registro `pending` huérfano bloquearía el job para siempre. `completed` y `failed` son finales.

- **Candado atómico**: el índice único parcial `job_runs_one_active_idx` (`job_name` donde `status` es `pending` o
  `processing`) admite como mucho una ejecución activa por job. `create_job_run` **es** la adquisición: el `INSERT`
  del registro `pending` lo decide la base; el proceso que pierde recibe una violación de unicidad
  (`JobAlreadyRunning`) y no crea ninguna fila. No hay «consultar y luego insertar».
- **Transiciones atómicas**: `update_job_status` es un `UPDATE … WHERE id = :id AND status IN (<orígenes válidos>)`
  (*compare-and-set*). Si otra ejecución ya cambió el estado, no actualiza nada y lanza `InvalidTransition`.
- **Idempotencia** por `(job_name, target_date)`: `has_completed_for_date`. `acquire_job_run` lo comprueba otra vez
  **dentro** de la transacción de adquisición, cuando ya tiene el candado, así dos procesos no repiten una fecha
  aunque uno termine justo entre la comprobación del otro y su adquisición.
- **Ejecuciones abandonadas**: un `SIGKILL` o una caída del servidor no ejecutan ningún `except` ni `finally`, y el
  registro se queda activo. `recover_abandoned_runs` marca `failed` (`abandoned`) las activas de más de
  `STALE_AFTER`; `acquire_job_run` la llama antes de adquirir.

- **PostgreSQL / Supabase** (`DATABASE_URL`): la tabla la crea la migración `migrations/20261115120000_job_runs.sql`
  (restricciones, índices, RLS). Este módulo nunca la crea ni la altera.
- **SQLite** (sin `DATABASE_URL`, desarrollo local y tests): crea una tabla equivalente al primer uso, con los mismos
  `CHECK` de estado y el mismo índice único parcial.
"""

import re
import uuid
import weakref
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Engine,
    Index,
    MetaData,
    Table,
    Text,
    Uuid,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import get_engine

TABLE_NAME = "job_runs"
MIGRATION_FILE = "migrations/20261115120000_job_runs.sql"

PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
STATUSES = (PENDING, PROCESSING, COMPLETED, FAILED)
# Estados que retienen el candado (los que cubre el índice único parcial).
ACTIVE_STATUSES = (PENDING, PROCESSING)

# Transiciones permitidas: estado de origen → destinos. Los estados finales no tienen salida.
TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING: frozenset({PROCESSING, FAILED}),
    PROCESSING: frozenset({COMPLETED, FAILED}),
    COMPLETED: frozenset(),
    FAILED: frozenset(),
}

# Una ejecución activa durante más de este tiempo se da por abandonada (el proceso murió sin poder cerrarla). Debe
# superar con margen la duración máxima legítima de un job: en `nightly_export`, el timeout del pipeline (30 min) más
# la exportación de un día.
STALE_AFTER = timedelta(hours=2)
ABANDONED = "abandoned: la ejecución seguía activa sin terminar; el proceso cayó sin poder cerrarla"

MAX_ERROR_LENGTH = 1000
_JOB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Mismas expresiones que la migración, para que SQLite rechace lo mismo que PostgreSQL.
_ACTIVE_WHERE = "status in ('pending', 'processing')"
_STATUS_CHECK = "status in ('pending', 'processing', 'completed', 'failed')"
_STARTED_CHECK = (
    "case status when 'pending' then started_at is null when 'failed' then 1 = 1 else started_at is not null end"
)
_FINISHED_CHECK = "(status in ('completed', 'failed')) = (finished_at is not null)"
_ERROR_CHECK = "status = 'failed' or error_message is null"
_TIMES_CHECK = "finished_at is null or started_at is null or finished_at >= started_at"

metadata = MetaData()

job_runs = Table(
    TABLE_NAME,
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("job_name", Text, nullable=False),
    Column("target_date", Date, nullable=False),
    Column("status", Text, nullable=False, default=PENDING),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(_STATUS_CHECK, name="job_runs_status_check"),
    CheckConstraint(_STARTED_CHECK, name="job_runs_started_check"),
    CheckConstraint(_FINISHED_CHECK, name="job_runs_finished_check"),
    CheckConstraint(_ERROR_CHECK, name="job_runs_error_check"),
    CheckConstraint(_TIMES_CHECK, name="job_runs_times_check"),
    Index("job_runs_job_name_target_date_idx", "job_name", "target_date"),
    Index(
        "job_runs_one_active_idx",
        "job_name",
        unique=True,
        sqlite_where=text(_ACTIVE_WHERE),
        postgresql_where=text(_ACTIVE_WHERE),
    ),
)


class JobRunsStorageError(Exception):
    """No se ha podido leer o escribir `job_runs` (base caída, migración sin aplicar, permisos…).

    El mensaje solo dice el tipo de error y su SQLSTATE, nunca la cadena de conexión ni los valores.
    """


class JobAlreadyRunning(Exception):
    """Otra ejecución del mismo job está activa (`pending` o `processing`): no se ha adquirido el candado."""

    def __init__(self, job_name: str, active: dict[str, Any] | None) -> None:
        super().__init__(f"Ya hay una ejecución activa de {job_name}.")
        self.job_name = job_name
        self.active = active


class JobAlreadyCompleted(Exception):
    """El job ya terminó correctamente para esa fecha: no se repite (idempotencia)."""

    def __init__(self, job_name: str, target_date: date) -> None:
        super().__init__(f"{job_name} ya está completado para {target_date.isoformat()}.")
        self.job_name = job_name
        self.target_date = target_date


class InvalidTransition(Exception):
    """El cambio de estado pedido no está permitido desde el estado actual (o la ejecución no existe)."""

    def __init__(self, run_id: uuid.UUID, current: str | None, new: str) -> None:
        super().__init__(f"Transición no permitida en la ejecución {run_id}: {current or 'inexistente'} → {new}.")
        self.run_id = run_id
        self.current = current
        self.new = new


def error_summary(error: BaseException) -> str:
    """Texto seguro para `error_message` y para el log: tipo y resumen, sin credenciales ni SQL con valores.

    De un error de SQLAlchemy solo se guarda el tipo del error del driver y su SQLSTATE (su texto puede incluir la
    sentencia, los parámetros o el host). Del resto, tipo y mensaje en una línea, recortados.
    """
    if isinstance(error, SQLAlchemyError):
        cause = getattr(error, "orig", None) or error
        sqlstate = getattr(cause, "sqlstate", None)
        return type(cause).__name__ + (f" (SQLSTATE {sqlstate})" if sqlstate else "")
    if isinstance(error, JobRunsStorageError):
        return f"JobRunsStorageError: {error}"
    message = " ".join(str(error).split())
    summary = f"{type(error).__name__}: {message}" if message else type(error).__name__
    return summary[:MAX_ERROR_LENGTH]


def _storage_error(error: SQLAlchemyError) -> JobRunsStorageError:
    return JobRunsStorageError(error_summary(error))


# Motores SQLite en los que ya se ha creado la tabla (los tests usan una base distinta en cada test).
_sqlite_ready: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def job_runs_engine() -> Engine:
    """Motor de la base de `DATABASE_URL` (la misma configuración que el resto de la API). En SQLite crea la tabla."""
    engine = get_engine()
    if engine.dialect.name == "sqlite" and engine not in _sqlite_ready:
        metadata.create_all(engine)
        _sqlite_ready.add(engine)
    return engine


def _utc(value: datetime | None) -> datetime | None:
    # SQLite devuelve fechas sin zona: se guardan siempre en UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _as_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row._mapping)
    for key in ("started_at", "finished_at", "created_at"):
        data[key] = _utc(data[key])
    return data


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _check_job_name(job_name: str) -> None:
    if not _JOB_NAME.match(job_name):
        raise ValueError(f"Nombre de job no válido: {job_name!r} (minúsculas, dígitos y _; empieza por letra).")


def _is_unique_violation(error: IntegrityError) -> bool:
    cause = getattr(error, "orig", None)
    if getattr(cause, "sqlstate", None) == "23505":
        return True
    return "UNIQUE constraint failed" in str(cause)  # SQLite


# --- Consultas ----------------------------------------------------------------------------------------------------


def get_job_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    """Ejecución por id, o `None`."""
    try:
        with job_runs_engine().connect() as connection:
            row = connection.execute(select(job_runs).where(job_runs.c.id == run_id)).first()
    except SQLAlchemyError as error:
        raise _storage_error(error) from None
    return _as_dict(row)


def get_active_job_run(job_name: str) -> dict[str, Any] | None:
    """Ejecución que retiene el candado del job (`pending` o `processing`), o `None`. Como mucho hay una."""
    statement = select(job_runs).where(job_runs.c.job_name == job_name, job_runs.c.status.in_(ACTIVE_STATUSES))
    try:
        with job_runs_engine().connect() as connection:
            row = connection.execute(statement).first()
    except SQLAlchemyError as error:
        raise _storage_error(error) from None
    return _as_dict(row)


def has_processing_lock(job_name: str) -> bool:
    """¿Hay una ejecución activa del job? Solo informativo: **no** sirve para adquirir (eso es `create_job_run`)."""
    return get_active_job_run(job_name) is not None


def _completed_statement(job_name: str, target_date: date):
    return (
        select(job_runs.c.id)
        .where(
            job_runs.c.job_name == job_name,
            job_runs.c.target_date == target_date,
            job_runs.c.status == COMPLETED,
        )
        .limit(1)
    )


def has_completed_for_date(job_name: str, target_date: date) -> bool:
    """¿Hay una ejecución `completed` del job para ese día? (Usa el índice `(job_name, target_date)`.)"""
    try:
        with job_runs_engine().connect() as connection:
            return connection.execute(_completed_statement(job_name, target_date)).first() is not None
    except SQLAlchemyError as error:
        raise _storage_error(error) from None


def list_job_runs(job_name: str, target_date: date | None = None) -> list[dict[str, Any]]:
    """Historial del job (opcionalmente de un día), del más antiguo al más reciente."""
    statement = select(job_runs).where(job_runs.c.job_name == job_name)
    if target_date is not None:
        statement = statement.where(job_runs.c.target_date == target_date)
    statement = statement.order_by(job_runs.c.created_at, job_runs.c.id)
    try:
        with job_runs_engine().connect() as connection:
            return [_as_dict(row) for row in connection.execute(statement)]
    except SQLAlchemyError as error:
        raise _storage_error(error) from None


# --- Escrituras ---------------------------------------------------------------------------------------------------


def _insert_pending(connection, job_name: str, target_date: date, created_at: datetime) -> dict[str, Any]:
    run_id = uuid.uuid4()
    row = connection.execute(
        job_runs.insert()
        .values(id=run_id, job_name=job_name, target_date=target_date, status=PENDING, created_at=created_at)
        .returning(*job_runs.c)
    ).first()
    return _as_dict(row)


def create_job_run(job_name: str, target_date: date, *, now: datetime | None = None) -> dict[str, Any]:
    """Registra una ejecución `pending` y la devuelve. **Es la adquisición atómica del candado.**

    `JobAlreadyRunning` si el job ya tiene una ejecución activa (de este o de otro proceso): lo decide el índice
    único parcial en el propio `INSERT`, y el proceso que pierde no deja ninguna fila.
    """
    _check_job_name(job_name)
    try:
        with job_runs_engine().begin() as connection:
            return _insert_pending(connection, job_name, target_date, _now(now))
    except IntegrityError as error:
        if _is_unique_violation(error):
            raise JobAlreadyRunning(job_name, _safe_active(job_name)) from None
        raise _storage_error(error) from None
    except SQLAlchemyError as error:
        raise _storage_error(error) from None


def _safe_active(job_name: str) -> dict[str, Any] | None:
    # Solo para informar en el log de quién tiene el candado: si la lectura falla, no tapa el conflicto.
    try:
        return get_active_job_run(job_name)
    except JobRunsStorageError:
        return None


def recover_abandoned_runs(job_name: str, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Marca `failed` (`abandoned`) las ejecuciones activas del job de más de `STALE_AFTER`. Devuelve las marcadas.

    Recupera el caso que ningún `except`/`finally` puede cubrir: el proceso murió (`SIGKILL`, OOM, reinicio del
    servidor) con la ejecución activa. La antigüedad se mide desde `started_at` (o `created_at` si no llegó a empezar).
    """
    current = _now(now)
    limit = current - STALE_AFTER
    table = job_runs
    statement = (
        update(table)
        .where(
            table.c.job_name == job_name,
            table.c.status.in_(ACTIVE_STATUSES),
            # `started_at` es nulo en `pending`: entonces cuenta desde la creación.
            ((table.c.started_at.is_not(None)) & (table.c.started_at < limit))
            | ((table.c.started_at.is_(None)) & (table.c.created_at < limit)),
        )
        .values(status=FAILED, finished_at=current, error_message=ABANDONED)
        .returning(*table.c)
    )
    try:
        with job_runs_engine().begin() as connection:
            return [_as_dict(row) for row in connection.execute(statement)]
    except SQLAlchemyError as error:
        raise _storage_error(error) from None


def acquire_job_run(job_name: str, target_date: date, *, now: datetime | None = None) -> dict[str, Any]:
    """Adquiere una ejecución del job para `target_date`: devuelve el registro `pending` recién creado.

    1. Recupera las ejecuciones abandonadas (transacción propia).
    2. En **una** transacción: inserta el `pending` (candado; `JobAlreadyRunning` si otro lo tiene) y, ya con el
       candado, comprueba si la fecha está completada. Si lo está, deshace el `INSERT` (no queda fila) y lanza
       `JobAlreadyCompleted`.

    En PostgreSQL (READ COMMITTED) la consulta del paso 2 ve todo lo confirmado antes de ella: si otro proceso
    completó la fecha mientras este esperaba el candado, se detecta aquí y no se repite el trabajo.
    """
    _check_job_name(job_name)
    current = _now(now)
    recover_abandoned_runs(job_name, now=current)
    try:
        with job_runs_engine().begin() as connection:
            run = _insert_pending(connection, job_name, target_date, current)
            if connection.execute(_completed_statement(job_name, target_date)).first() is not None:
                raise JobAlreadyCompleted(job_name, target_date)  # sale del `with` → ROLLBACK del INSERT
            return run
    except IntegrityError as error:
        if _is_unique_violation(error):
            raise JobAlreadyRunning(job_name, _safe_active(job_name)) from None
        raise _storage_error(error) from None
    except SQLAlchemyError as error:
        raise _storage_error(error) from None


def update_job_status(
    run_id: uuid.UUID,
    new_status: str,
    *,
    error_message: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cambia el estado de una ejecución y devuelve el registro actualizado.

    Es un *compare-and-set*: el `UPDATE` solo aplica si el estado actual es un origen válido de `new_status`
    (`TRANSITIONS`); si no, `InvalidTransition` (también si la ejecución no existe). Registra los tiempos:
    `processing` → `started_at`; `completed`/`failed` → `finished_at`. `failed` exige `error_message`.
    """
    if new_status not in STATUSES:
        raise ValueError(f"Estado no válido: {new_status!r}.")
    sources = [status for status, targets in TRANSITIONS.items() if new_status in targets]
    if not sources:
        raise InvalidTransition(run_id, None, new_status)  # `pending` no es destino de ninguna transición
    if new_status == FAILED and not error_message:
        raise ValueError("Una ejecución fallida necesita error_message.")
    current = _now(now)
    values: dict[str, Any] = {"status": new_status}
    if new_status == PROCESSING:
        values["started_at"] = current
    if new_status in (COMPLETED, FAILED):
        values["finished_at"] = current
    if new_status == FAILED:
        values["error_message"] = error_message[:MAX_ERROR_LENGTH]
    statement = (
        update(job_runs)
        .where(job_runs.c.id == run_id, job_runs.c.status.in_(sources))
        .values(**values)
        .returning(*job_runs.c)
    )
    try:
        with job_runs_engine().begin() as connection:
            row = connection.execute(statement).first()
    except SQLAlchemyError as error:
        raise _storage_error(error) from None
    if row is None:
        existing = get_job_run(run_id)
        raise InvalidTransition(run_id, existing["status"] if existing else None, new_status)
    return _as_dict(row)
