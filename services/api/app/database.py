"""Persistencia en TinyDB (ficheros JSON en disco).

- Directorio de proveedores: `services/api/db/suppliers.json`, variable `SUPPLIERS_DB_PATH`.
- Usuarios y perfiles (autenticación): `services/api/db/auth.json`, variable `AUTH_DB_PATH`. Es la única fuente de
  verdad de `User` y `Profile`: no hay tablas de usuarios en ninguna otra base de datos. En el mismo fichero viven
  los enlaces de recuperación de contraseña (`password_reset_tokens`, AUTH-03).
- Gestor de incidencias: `services/api/db/incidents.json`, variable `INCIDENTS_DB_PATH`.

Los ficheros están ignorados en git; los tests apuntan las variables a ficheros temporales.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tinydb import TinyDB
from tinydb.table import Table

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "suppliers.json"
SUPPLIERS_TABLE = "suppliers"

# TinyDB no es seguro entre hilos y FastAPI ejecuta los endpoints síncronos en un pool de hilos: se serializa el
# acceso al fichero para que una lectura nunca vea una escritura a medias.
_lock = threading.Lock()


def get_db_path() -> Path:
    return Path(os.environ.get("SUPPLIERS_DB_PATH", DEFAULT_DB_PATH))


@contextmanager
def suppliers_table() -> Iterator[Table]:
    """Abre la base de datos, entrega la tabla `suppliers` y la cierra al terminar.

    Se abre en cada uso (y no una instancia global) para leer siempre el estado del disco, también si otro
    proceso —p. ej. el seeder— lo ha modificado con la API arrancada.
    """
    with _lock:
        db = TinyDB(get_db_path(), create_dirs=True, encoding="utf-8", ensure_ascii=False, indent=2)
        try:
            yield db.table(SUPPLIERS_TABLE)
        finally:
            db.close()


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
    with _auth_lock:
        db = TinyDB(get_auth_db_path(), create_dirs=True, encoding="utf-8", ensure_ascii=False, indent=2)
        try:
            yield db
        finally:
            db.close()


DEFAULT_INCIDENTS_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "incidents.json"
INCIDENTS_TABLE = "incidents"

# Candado propio, por el mismo motivo que el de usuarios: validar el token no debe esperar a las incidencias.
_incidents_lock = threading.Lock()


def get_incidents_db_path() -> Path:
    return Path(os.environ.get("INCIDENTS_DB_PATH", DEFAULT_INCIDENTS_DB_PATH))


@contextmanager
def incidents_table() -> Iterator[Table]:
    """Abre la base del gestor de incidencias, entrega la tabla `incidents` y la cierra al terminar."""
    with _incidents_lock:
        db = TinyDB(get_incidents_db_path(), create_dirs=True, encoding="utf-8", ensure_ascii=False, indent=2)
        try:
            yield db.table(INCIDENTS_TABLE)
        finally:
            db.close()
