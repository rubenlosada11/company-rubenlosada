# TrackFlow API — Directorio de proveedores

Servicio FastAPI + Pydantic + TinyDB. Documentación completa pendiente (se completa al cerrar el directorio de
proveedores).

## Seeder

Desde `services/api`:

```bash
uv run seed
```

Carga los **15 proveedores iniciales** de [`CONTEXT-directorio.md`](../../CONTEXT-directorio.md) (definidos en
[`app/seed.py`](./app/seed.py); un test comprueba que son idénticos a los del CONTEXT). Cada uno pasa por el mismo
modelo Pydantic que la API y recibe su `updated_at` del servidor.

Es **idempotente**: identifica cada proveedor por `(name, country)` (el nombre sin distinguir mayúsculas) e inserta
solo los que falten. Los existentes no se modifican, así que no pisa tarifas ni estados cambiados desde la API.

Primera ejecución sobre una base vacía:

```text
Seeder completed.
Inserted: 15
Skipped: 0
Total: 15
```

Segunda ejecución: `Inserted: 0`, `Skipped: 15`, `Total: 15`. Antes del resumen lista cada proveedor con `+`
(insertado) o `=` (ya existía). Para empezar de cero, borra `db/suppliers.json` y vuelve a ejecutarlo.

> El candado de `app/database.py` protege las peticiones dentro de la API, no entre procesos: ejecuta el seeder con
> la API parada o sin estar editando proveedores a la vez.

## Persistencia

Los datos se guardan con **TinyDB** en un fichero JSON en disco, así que sobreviven a los reinicios de la API:

| | |
| --- | --- |
| Ruta por defecto | `services/api/db/suppliers.json` (la carpeta se crea sola) |
| Tabla | `suppliers` (el `id` de cada proveedor es el `doc_id` que asigna TinyDB) |
| Cambiar la ruta | variable de entorno `SUPPLIERS_DB_PATH` (los tests usan un fichero temporal) |
| Git | `db/` está en `.gitignore`: la base local no se versiona |

El acceso está en [`app/database.py`](./app/database.py): cada uso abre el fichero, trabaja con la tabla y lo
cierra, con un candado para que las peticiones concurrentes no corrompan el JSON.
