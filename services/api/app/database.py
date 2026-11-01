"""Persistencia: TinyDB (ficheros JSON en disco) y, para el inventario, una base SQL con SQLModel.

TinyDB:

- Directorio de proveedores: `services/api/db/suppliers.json`, variable `SUPPLIERS_DB_PATH`.
- Usuarios y perfiles (autenticación): `services/api/db/auth.json`, variable `AUTH_DB_PATH`. Es la única fuente de
  verdad de `User` y `Profile`: no hay tablas de usuarios en ninguna otra base de datos. En el mismo fichero viven
  los enlaces de recuperación de contraseña (`password_reset_tokens`, AUTH-03).
- Gestor de incidencias: `services/api/db/incidents.json`, variable `INCIDENTS_DB_PATH`.

SQL (SQLModel, Hito 5): SKUs y movimientos de stock del inventario. Por defecto, SQLite en
`services/api/db/inventory.db`; con `DATABASE_URL` se usa otra base (p. ej. PostgreSQL de Supabase). Ver
`get_engine` y `get_db`.

Los ficheros están ignorados en git; los tests apuntan las variables a ficheros temporales.

Si un fichero no se puede abrir, leer o escribir (permisos, disco, JSON corrupto) se lanza `StorageError`, que dice qué
base falla y por qué. La API lo convierte en un 500 genérico y los scripts, en un mensaje y un código de salida 1.
"""

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, event, make_url
from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB
from tinydb.table import Table

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "suppliers.json"
SUPPLIERS_TABLE = "suppliers"

# TinyDB no es seguro entre hilos y FastAPI ejecuta los endpoints síncronos en un pool de hilos: se serializa el
# acceso al fichero para que una lectura nunca vea una escritura a medias.
_lock = threading.Lock()


class StorageError(Exception):
    """El fichero de una base TinyDB no se puede abrir, leer o escribir.

    El mensaje lleva la ruta y el motivo, nunca el contenido del fichero. Es para el log o la consola: no se envía al
    cliente de la API.
    """

    def __init__(self, path: Path, cause: Exception):
        super().__init__(f"No se puede usar la base de datos {path}: {_storage_reason(cause)}.")
        self.path = path


# Fallos del fichero: sistema de ficheros (permisos, disco lleno, ruta no válida) y contenido que no es JSON en UTF-8.
_STORAGE_FAILURES = (OSError, json.JSONDecodeError, UnicodeDecodeError)


def _storage_reason(cause: Exception) -> str:
    if isinstance(cause, json.JSONDecodeError):
        return f"el fichero no contiene JSON válido (línea {cause.lineno}, columna {cause.colno})"
    if isinstance(cause, UnicodeDecodeError):
        return "el fichero no está codificado en UTF-8"
    return getattr(cause, "strerror", None) or type(cause).__name__


@contextmanager
def _open_db(path: Path, lock: threading.Lock) -> Iterator[TinyDB]:
    """Abre un fichero TinyDB bajo su candado y lo cierra al terminar. Los fallos del fichero salen como `StorageError`.

    TinyDB lee el fichero al usar una tabla, no al abrirlo: por eso también se vigila el bloque que usa la base.
    """
    with lock:
        try:
            db = TinyDB(path, create_dirs=True, encoding="utf-8", ensure_ascii=False, indent=2)
        except _STORAGE_FAILURES as error:
            raise StorageError(path, error) from error
        try:
            yield db
        except _STORAGE_FAILURES as error:
            raise StorageError(path, error) from error
        finally:
            db.close()


def get_db_path() -> Path:
    return Path(os.environ.get("SUPPLIERS_DB_PATH", DEFAULT_DB_PATH))


@contextmanager
def suppliers_table() -> Iterator[Table]:
    """Abre la base de datos, entrega la tabla `suppliers` y la cierra al terminar.

    Se abre en cada uso (y no una instancia global) para leer siempre el estado del disco, también si otro
    proceso —p. ej. el seeder— lo ha modificado con la API arrancada.
    """
    with _open_db(get_db_path(), _lock) as db:
        yield db.table(SUPPLIERS_TABLE)


def get_suppliers_table() -> Iterator[Table]:
    """Dependencia de FastAPI: `table: Table = Depends(get_suppliers_table)`."""
    with suppliers_table() as table:
        yield table


DEFAULT_AUTH_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "auth.json"

# Candado propio: las rutas de proveedores retienen `_lock` durante toda la petición (dependencia con `yield`) y
# también validan el token, que lee usuarios. Con un único candado no reentrante se bloquearían a sí mismas.
_auth_lock = threading.Lock()


def get_auth_db_path() -> Path:
    return Path(os.environ.get("AUTH_DB_PATH", DEFAULT_AUTH_DB_PATH))


@contextmanager
def auth_db() -> Iterator[TinyDB]:
    """Abre la base de usuarios (tablas `users`, `profiles` y `password_reset_tokens`) y la cierra al terminar.

    Se entrega la base completa para que las operaciones que tocan varias tablas (crear o borrar un usuario y su
    perfil, usar un enlace de recuperación y cambiar la contraseña) ocurran bajo el mismo candado.
    """
    with _open_db(get_auth_db_path(), _auth_lock) as db:
        yield db


DEFAULT_INCIDENTS_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "incidents.json"
INCIDENTS_TABLE = "incidents"

# Candado propio, por el mismo motivo que el de usuarios: validar el token no debe esperar a las incidencias.
_incidents_lock = threading.Lock()


def get_incidents_db_path() -> Path:
    return Path(os.environ.get("INCIDENTS_DB_PATH", DEFAULT_INCIDENTS_DB_PATH))


@contextmanager
def incidents_table() -> Iterator[Table]:
    """Abre la base del gestor de incidencias, entrega la tabla `incidents` y la cierra al terminar."""
    with _open_db(get_incidents_db_path(), _incidents_lock) as db:
        yield db.table(INCIDENTS_TABLE)


# --- Inventario (Hito 5): SQLModel ---------------------------------------------------------------------------------

DEFAULT_INVENTORY_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "inventory.db"
POSTGRES_CONNECT_TIMEOUT_SECONDS = 10

# Un solo motor a la vez: se crea al primer uso y se sustituye si cambia `DATABASE_URL` (los tests usan una base
# temporal por test). El candado evita crear dos motores a la vez desde dos hilos.
_engine_lock = threading.Lock()
_engine: Engine | None = None
_engine_url: str | None = None


def get_database_url() -> str:
    """URL de SQLAlchemy de la base del inventario: `DATABASE_URL` o, si no está, el SQLite local."""
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or f"sqlite:///{DEFAULT_INVENTORY_DB_PATH.as_posix()}"


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    # SQLite no comprueba las claves foráneas si no se le pide en cada conexión.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    """Motor SQLModel de la base del inventario. La primera vez crea las tablas que falten (`create_all`).

    Las tablas se crean al primer uso y no al arrancar la API: si la base no está disponible, solo falla el
    inventario, no el resto de módulos. `create_all` no modifica tablas que ya existen (no es una migración).
    """
    global _engine, _engine_url
    url = get_database_url()
    with _engine_lock:
        if _engine is not None and _engine_url == url:
            return _engine
        if _engine is not None:
            _engine.dispose()

        if url.startswith("sqlite"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            # FastAPI ejecuta los endpoints síncronos en un pool de hilos: la conexión no es de un solo hilo.
            engine = create_engine(url, connect_args={"check_same_thread": False})
            event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        else:
            # `pool_pre_ping`: descarta conexiones cerradas por el servidor (p. ej. el pooler de Supabase).
            # Con psycopg, una base inalcanzable falla a los pocos segundos en vez de dejar la petición colgada.
            is_psycopg = make_url(url).get_driver_name() == "psycopg"
            connect_args = {"connect_timeout": POSTGRES_CONNECT_TIMEOUT_SECONDS} if is_psycopg else {}
            engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

        # Registra las tablas (SKU, StockEntry, StockExit) en `SQLModel.metadata` antes de crearlas.
        import app.inventory_models  # noqa: F401

        SQLModel.metadata.create_all(engine)
        _engine, _engine_url = engine, url
        return engine


def dispose_engine() -> None:
    """Cierra las conexiones del motor actual (lo usan los tests al terminar cada uno)."""
    global _engine, _engine_url
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine, _engine_url = None, None


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: `session: Session = Depends(get_db)`. Una sesión por petición, cerrada al terminar."""
    with Session(get_engine()) as session:
        yield session
