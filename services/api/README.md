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

## API

Arranque: `uv run uvicorn app.main:app --reload --port 8000` → Swagger UI en http://localhost:8000/docs.

| Método y ruta | Respuesta |
| --- | --- |
| `POST /suppliers` | 201 con el proveedor creado (`id` de TinyDB, `updated_at` del servidor) · 422 si los datos no son válidos |
| `GET /suppliers` | 200 con todos · filtros opcionales y combinables `?country=USA\|Spain` y `?category=<categoría>` · 422 si el valor del filtro no existe |
| `GET /suppliers/{id}` | 200 · 404 si no existe |
| `PATCH /suppliers/{id}/rate` | 200 con la nueva tarifa y `updated_at` renovado · 422 si la tarifa no es > 0 · 404 |
| `PATCH /suppliers/{id}/status` | 200 (`active` / `suspended`; no cambia `updated_at`) · 422 · 404 |
| `DELETE /suppliers/{id}` | 204 · 404 (el flujo habitual es suspender; la UI no ofrece borrar) |

CORS: solo el backoffice local (`http://localhost:3002`, `http://127.0.0.1:3002`). Se cambia con la variable
`CORS_ALLOWED_ORIGINS` (orígenes separados por comas).

**Limitación conocida:** si se borra el proveedor con el `id` más alto, TinyDB reutiliza ese `id` en el siguiente
alta (calcula el siguiente como máximo + 1).

## Tests

```bash
uv run pytest -q
```

116 tests (modelos, persistencia, seeder y API con `TestClient`), cada uno sobre una base temporal: nunca tocan
`db/suppliers.json`.

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
