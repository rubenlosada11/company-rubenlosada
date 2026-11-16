"""Dead Letter Queue (DLQ) persistente: las tareas que han fallado **definitivamente**, en la tabla `task_dead_letters`.

Una tarea llega aquí una sola vez, cuando Celery ya no la va a volver a ejecutar:

- `retries_exhausted`: fallo transitorio que persistió tras el intento inicial y los 3 reintentos.
- `permanent_error`: error no recuperable (datos no válidos, tabla inexistente, un bug): no se reintenta.
- `time_limit`: superó el tiempo máximo de ejecución (`app/celery_app.py`).
- `expired`: caducó en la cola sin que ningún worker la empezara.

No basta con el log ni con el estado `FAILURE` de Celery: el log rota y el result backend caduca a las 24 h. Esta tabla
vive en la base de `DATABASE_URL` (la misma del pipeline: PostgreSQL/Supabase, o SQLite en local) y sobrevive al
worker, a Redis y a los reinicios.

- **Idempotencia:** `task_id` es único y la inserción es `INSERT … ON CONFLICT (task_id) DO NOTHING`. Si el mismo
  fallo se notifica dos veces (p. ej. el worker muere después de escribir y antes de confirmar el mensaje, y Celery lo
  entrega otra vez), la segunda escritura no hace nada y lo registra como `dead_letter_duplicate`.
- **Sin secretos:** se guarda el mensaje completo del error con las credenciales de URLs (`://usuario:clave@`) y los
  pares `password=…`/`token=…` censurados, y solo los argumentos escalares de la tarea (identificadores y parámetros).
- **Si la base no responde** (justo el caso de muchos fallos transitorios), la escritura se reintenta dos veces y, si
  sigue fallando, el registro completo sale en el log como `dead_letter_not_persisted` (nivel CRITICAL). Es la única
  situación en la que un fallo definitivo queda solo en el log.

- **PostgreSQL / Supabase**: la tabla la crea la migración `migrations/20261116120000_task_dead_letters.sql`.
- **SQLite** (sin `DATABASE_URL`, desarrollo local y tests): se crea una tabla equivalente al primer uso.
"""

import logging
import re
import time
import uuid
import weakref
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Engine,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.reporting.tables import is_transient
from app.tasks.observability import log_event

TABLE_NAME = "task_dead_letters"
MIGRATION_FILE = "migrations/20261116120000_task_dead_letters.sql"

RETRIES_EXHAUSTED = "retries_exhausted"
PERMANENT_ERROR = "permanent_error"
TIME_LIMIT = "time_limit"
EXPIRED = "expired"
REASONS = (RETRIES_EXHAUSTED, PERMANENT_ERROR, TIME_LIMIT, EXPIRED)

MAX_ERROR_LENGTH = 4000
MAX_ARGUMENT_LENGTH = 200
# Esperas entre intentos de escritura en la DLQ si la base falla de forma transitoria.
WRITE_RETRY_DELAYS = (0.5, 2.0)

_REASON_CHECK = "reason in ('retries_exhausted', 'permanent_error', 'time_limit', 'expired')"

metadata = MetaData()

task_dead_letters = Table(
    TABLE_NAME,
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("task_id", Text, nullable=False),
    Column("task_name", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("attempts", Integer, nullable=True),
    Column("max_retries", Integer, nullable=True),
    Column("exception_type", Text, nullable=False),
    Column("error_message", Text, nullable=False),
    Column("task_kwargs", JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
    Column("worker", Text, nullable=True),
    Column("failed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("task_id", name="task_dead_letters_task_id_key"),
    CheckConstraint(_REASON_CHECK, name="task_dead_letters_reason_check"),
    CheckConstraint("attempts is null or attempts >= 1", name="task_dead_letters_attempts_check"),
    Index("task_dead_letters_failed_at_idx", "failed_at"),
)


class DeadLetterStorageError(Exception):
    """No se ha podido leer o escribir `task_dead_letters`. El mensaje es el tipo de error y su SQLSTATE."""


def _storage_error(error: SQLAlchemyError) -> DeadLetterStorageError:
    cause = getattr(error, "orig", None) or error
    sqlstate = getattr(cause, "sqlstate", None)
    return DeadLetterStorageError(type(cause).__name__ + (f" (SQLSTATE {sqlstate})" if sqlstate else ""))


_sqlite_ready: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def dead_letters_engine() -> Engine:
    """Motor de `DATABASE_URL`. En SQLite crea la tabla la primera vez; en PostgreSQL la crea la migración."""
    engine = get_engine()
    if engine.dialect.name == "sqlite" and engine not in _sqlite_ready:
        metadata.create_all(engine)
        _sqlite_ready.add(engine)
    return engine


# --- Censura de datos sensibles --------------------------------------------------------------------------------------

_URL_CREDENTIALS = re.compile(r"(?P<scheme>\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]+@")
_SECRET_PAIRS = re.compile(
    r"(?i)\b(?P<key>password|passwd|pwd|secret|token|api[_-]?key|authorization)(?P<sep>\s*[=:]\s*)[^\s,;&'\"]+"
)
_SENSITIVE_ARGUMENT = re.compile(r"(?i)password|secret|token|key|authorization|email")


def redact(text: str) -> str:
    """Quita credenciales de un texto (URLs con usuario y clave, `password=…`, `token: …`) y lo recorta."""
    text = _URL_CREDENTIALS.sub(lambda match: f"{match['scheme']}***@", text)
    text = _SECRET_PAIRS.sub(lambda match: f"{match['key']}{match['sep']}***", text)
    return text if len(text) <= MAX_ERROR_LENGTH else text[: MAX_ERROR_LENGTH - 1] + "…"


def safe_kwargs(kwargs: dict[str, Any] | None) -> dict[str, Any]:
    """Argumentos útiles para diagnosticar: solo escalares, sin claves sensibles y con los textos recortados."""
    safe: dict[str, Any] = {}
    for key, value in (kwargs or {}).items():
        if _SENSITIVE_ARGUMENT.search(str(key)):
            safe[str(key)] = "***"
        elif value is None or isinstance(value, (bool, int, float)):
            safe[str(key)] = value
        elif isinstance(value, str):
            safe[str(key)] = value[:MAX_ARGUMENT_LENGTH]
        else:
            safe[str(key)] = f"<{type(value).__name__}>"
    return safe


def error_chain(error: BaseException) -> list[BaseException]:
    """La cadena de excepciones tal como la muestra Python: `__cause__` (`raise … from x`) y, si no hay, `__context__`
    salvo que se ocultara con `raise … from None`. Respetarlo importa: `ReportingStorageError` usa `from None` para no
    arrastrar la excepción del driver, que puede llevar la cadena de conexión o los valores de la consulta."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain and len(chain) < 10:
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    return chain


def describe_error(error: BaseException) -> tuple[str, str]:
    """(tipo de la causa raíz, mensaje completo de la cadena de excepciones), censurado."""
    chain = error_chain(error)
    message = " ← ".join(f"{type(item).__name__}: {item}" if str(item) else type(item).__name__ for item in chain)
    return type(chain[-1]).__name__, redact(message)


# --- Escritura y lectura ---------------------------------------------------------------------------------------------


def _insert(row: dict[str, Any]) -> bool:
    engine = dead_letters_engine()
    dialect = postgresql if engine.dialect.name == "postgresql" else sqlite
    # `RETURNING id` dice sin ambigüedad si se ha insertado (fila) o si ya existía (nada), en PostgreSQL y en SQLite.
    statement = (
        dialect.insert(task_dead_letters)
        .values(**row)
        .on_conflict_do_nothing(index_elements=["task_id"])
        .returning(task_dead_letters.c.id)
    )
    with engine.begin() as connection:
        return connection.execute(statement).first() is not None


def record(
    *,
    task_id: str,
    task_name: str,
    reason: str,
    error: BaseException,
    attempts: int | None,
    max_retries: int | None,
    kwargs: dict[str, Any] | None,
    worker: str | None,
    failed_at: datetime | None = None,
) -> bool:
    """Guarda el fallo definitivo de `task_id`. `True` si lo ha insertado; `False` si ya estaba (idempotencia).

    Reintenta los fallos transitorios de la base (`WRITE_RETRY_DELAYS`); si no lo consigue, `DeadLetterStorageError`.
    """
    if reason not in REASONS:
        raise ValueError(f"Motivo de DLQ no válido: {reason}")
    exception_type, message = describe_error(error)
    now = datetime.now(UTC)
    row = {
        "id": uuid.uuid4(),
        "task_id": task_id,
        "task_name": task_name,
        "reason": reason,
        "attempts": attempts,
        "max_retries": max_retries,
        "exception_type": exception_type,
        "error_message": message,
        "task_kwargs": safe_kwargs(kwargs),
        "worker": worker,
        "failed_at": failed_at or now,
        "created_at": now,
    }
    for delay in (*WRITE_RETRY_DELAYS, None):
        try:
            return _insert(row)
        except SQLAlchemyError as error_:
            if delay is None or not is_transient(error_):
                raise _storage_error(error_) from None
            time.sleep(delay)
    raise AssertionError("inalcanzable")  # pragma: no cover


def record_failure(**fields: Any) -> bool | None:
    """`record` para los ganchos de fallo de Celery: nunca lanza (un error aquí no debe tumbar el worker).

    Devuelve `True` (insertado), `False` (ya estaba) o `None` (no se pudo guardar: queda en el log como CRITICAL con
    todos sus datos, para no perder el fallo).
    """
    try:
        inserted = record(**fields)
    except Exception as error:  # noqa: BLE001 — se registra y se sigue
        exception_type, message = describe_error(fields["error"])
        log_event(
            "dead_letter_not_persisted",
            logging.CRITICAL,
            task_id=fields["task_id"],
            task_name=fields["task_name"],
            reason=fields["reason"],
            attempts=fields.get("attempts"),
            exception_type=exception_type,
            error_message=message,
            task_kwargs=safe_kwargs(fields.get("kwargs")),
            storage_error=str(error) if isinstance(error, DeadLetterStorageError) else type(error).__name__,
        )
        return None
    log_event(
        "dead_letter_recorded" if inserted else "dead_letter_duplicate",
        logging.ERROR if inserted else logging.WARNING,
        task_id=fields["task_id"],
        task_name=fields["task_name"],
        reason=fields["reason"],
        attempts=fields.get("attempts"),
    )
    return inserted


def get(task_id: str) -> dict[str, Any] | None:
    try:
        with dead_letters_engine().connect() as connection:
            row = connection.execute(
                select(task_dead_letters).where(task_dead_letters.c.task_id == task_id)
            ).first()
    except SQLAlchemyError as error:
        raise _storage_error(error) from None
    return dict(row._mapping) if row is not None else None


def latest(limit: int = 50) -> list[dict[str, Any]]:
    """Últimos fallos definitivos, del más reciente al más antiguo."""
    statement = (
        select(task_dead_letters)
        .order_by(task_dead_letters.c.failed_at.desc(), task_dead_letters.c.task_id)
        .limit(limit)
    )
    try:
        with dead_letters_engine().connect() as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]
    except SQLAlchemyError as error:
        raise _storage_error(error) from None
