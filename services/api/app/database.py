"""Persistencia del directorio de proveedores en TinyDB (un fichero JSON en disco).

Ruta por defecto: `services/api/db/suppliers.json` (ignorada en git). Se puede cambiar con la variable de entorno
`SUPPLIERS_DB_PATH` (los tests la apuntan a un fichero temporal).
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
