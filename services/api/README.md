# TrackFlow API — Directorio de proveedores y analizador de incidencias

API de TrackFlow con dos módulos:

- **Directorio de proveedores** (`/suppliers`): el registro centralizado que sustituye a las hojas de cálculo de Carlos
  Vega (Carrier Operations) y Ana Whitfield (Warehouse Operations) y unifica los mercados de USA y España. Fuente de
  verdad de campos, categorías, estados y datos iniciales: [`CONTEXT-directorio.md`](../../CONTEXT-directorio.md).
- **Analizador de incidencias** (`/api/incidents`): valida el CSV de incidencias de CX y calcula sus métricas con el
  paquete compartido [`packages/analisis-incidencias`](../../packages/analisis-incidencias/README.md). Ver
  [Analizador de incidencias](#analizador-de-incidencias).

**Stack:** Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), FastAPI, Pydantic y TinyDB (base de datos en un fichero
JSON). Sin ORM, Docker ni base de datos de servidor: TinyDB es una elección deliberada de este ejercicio. La consumen
las páginas `/proveedores` e `/incidencias` del [backoffice](../../uis/backoffice/README.md).

> Solo para uso **local**: no tiene autenticación. No publicarla sin añadirla antes (permite editar tarifas, estados
> y borrar, y subir CSV con correos de clientes). Instrucciones de despliegue (no ejecutadas):
> [`docs/despliegue-api.md`](../../docs/despliegue-api.md).

## Instalación

Requiere `uv` (`uv --version`). Desde la raíz del repo, en Windows PowerShell (un comando por línea):

```powershell
cd services\api
uv sync
```

`uv sync` crea `.venv/` e instala las versiones exactas de `uv.lock` (FastAPI, Pydantic, TinyDB, uvicorn,
python-multipart y el paquete local `analisis-incidencias` en modo editable; y pytest + httpx2 para los tests).

## Ejecución

```powershell
uv run seed
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 · Swagger UI (probar los endpoints desde el navegador): http://localhost:8000/docs
- Comprobación rápida: http://localhost:8000/health → `{"status":"ok"}`

Variables de entorno opcionales (todas tienen valor por defecto; no hace falta ningún `.env`):

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `SUPPLIERS_DB_PATH` | `services/api/db/suppliers.json` | Fichero de TinyDB |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3002,http://127.0.0.1:3002` | Orígenes del navegador autorizados (el backoffice). La API expone `Content-Disposition` para las descargas |

## Seeder

```powershell
uv run seed
```

Carga los **15 proveedores iniciales** de `CONTEXT-directorio.md` (copiados en [`app/seed.py`](./app/seed.py); un test
comprueba que son idénticos a los del CONTEXT). Cada uno pasa por el mismo modelo Pydantic que la API y recibe su
`updated_at` del servidor.

Es **idempotente**: identifica cada proveedor por `(name, country)` (el nombre sin distinguir mayúsculas) e inserta
solo los que falten. Los existentes no se modifican, así que no pisa tarifas ni estados cambiados desde la API.

Primera ejecución sobre una base vacía (lista cada proveedor con `+` y termina con el resumen):

```text
Base de datos: C:\...\services\api\db\suppliers.json
  + UPS Ground (USA)
  + FedEx Ground (USA)
  …
  + ReturnBear (USA)
Seeder completed.
Inserted: 15
Skipped: 0
Total: 15
```

Segunda ejecución: cada proveedor aparece como `= … (ya existe)` y el resumen es `Inserted: 0`, `Skipped: 15`,
`Total: 15`. Para empezar de cero, borra `db\suppliers.json` y vuelve a ejecutarlo.

> El candado de [`app/database.py`](./app/database.py) protege las peticiones dentro de la API, no entre procesos:
> ejecuta el seeder con la API parada o sin estar editando proveedores a la vez.

## Modelo de proveedor

| Campo | Tipo | Lo envía | Reglas |
| --- | --- | --- | --- |
| `id` | entero | servidor | `doc_id` que asigna TinyDB |
| `name` | texto | cliente, obligatorio | no vacío |
| `country` | texto | cliente, obligatorio | `USA` o `Spain` |
| `categories` | lista | cliente, obligatorio | al menos 1 de: `carrier_last_mile`, `carrier_international`, `warehouse_supplies`, `packaging_materials`, `reverse_logistics`, `fleet_maintenance`, `it_and_wms_software`, `cleaning_and_facilities` (los repetidos se eliminan) |
| `rate_per_shipment` | número | cliente, obligatorio | `> 0`, finito; no admite texto ni booleanos |
| `currency` | texto | cliente, obligatorio | `USD` si el país es `USA`, `EUR` si es `Spain` (otra combinación → 422) |
| `status` | texto | cliente, obligatorio | `active` o `suspended` |
| `service_zone` | texto o `null` | cliente, opcional | |
| `contact_email` | texto o `null` | cliente, opcional | formato básico `algo@dominio.tld` |
| `notes` | texto o `null` | cliente, opcional | |
| `updated_at` | fecha ISO 8601 (UTC) | servidor | se genera al crear y **cada vez que cambia la tarifa**; cambiar el estado no lo toca. Si el cliente lo envía, se ignora |

Modelos en [`app/models.py`](./app/models.py): `SupplierCreate`, `SupplierRateUpdate`, `SupplierStatusUpdate` y
`Supplier` (respuesta).

## API

Endpoints en [`app/routes/suppliers.py`](./app/routes/suppliers.py). Todas las respuestas son JSON en UTF-8.

| Método y ruta | Éxito | Errores |
| --- | --- | --- |
| `POST /suppliers` | 201 + proveedor creado | 422 datos no válidos |
| `GET /suppliers` | 200 + lista (filtros opcionales `country`, `category`) | 422 valor de filtro que no existe |
| `GET /suppliers/{id}` | 200 + proveedor | 404 |
| `PATCH /suppliers/{id}/rate` | 200 + proveedor con la nueva tarifa y `updated_at` renovado | 404 · 422 |
| `PATCH /suppliers/{id}/status` | 200 + proveedor con el nuevo estado | 404 · 422 |
| `DELETE /suppliers/{id}` | 204 sin cuerpo | 404 |

Los ejemplos de respuesta son salidas reales de la API con los datos del seeder.

### `GET /suppliers` y filtros

`country` (`USA`/`Spain`) y `category` (una de las 8 categorías) se pueden combinar; `category` devuelve los
proveedores que tienen esa categoría entre sus `categories`.

| Petición | Resultado con los datos del seeder |
| --- | --- |
| `GET /suppliers` | 15 proveedores |
| `GET /suppliers?country=Spain` | 6: MRW España, SEUR, DHL Express España, Nacex, Logística Inversa Iberia, Embalajes Zaragoza S.L. |
| `GET /suppliers?category=carrier_international` | 2: DHL Express USA, DHL Express España |
| `GET /suppliers?country=Spain&category=carrier_last_mile` | 4: MRW España, SEUR, DHL Express España, Nacex |
| `GET /suppliers?country=Mexico` | 422: `Input should be 'USA' or 'Spain'` |

`GET /suppliers?category=reverse_logistics` → 200:

```json
[
  {
    "name": "Logística Inversa Iberia",
    "country": "Spain",
    "categories": ["reverse_logistics"],
    "rate_per_shipment": 6.3,
    "currency": "EUR",
    "status": "active",
    "service_zone": null,
    "contact_email": "operaciones@liiberia.es",
    "notes": "Gestión de devoluciones para el almacén de Zaragoza.",
    "id": 12,
    "updated_at": "2026-09-27T22:34:26.592157Z"
  },
  {
    "name": "ReturnBear",
    "country": "USA",
    "categories": ["reverse_logistics"],
    "rate_per_shipment": 4.15,
    "currency": "USD",
    "status": "active",
    "service_zone": "West Coast",
    "contact_email": "partnerships@returnbear.com",
    "notes": "Gestión de devoluciones para clientes de Los Ángeles.",
    "id": 15,
    "updated_at": "2026-09-27T22:34:26.594619Z"
  }
]
```

### `GET /suppliers/{id}`

`GET /suppliers/11` → 200 con Nacex. `GET /suppliers/999` → 404:

```json
{ "detail": "Proveedor 999 no encontrado" }
```

### `POST /suppliers`

Cuerpo (sin `id` ni `updated_at`; los opcionales se pueden omitir):

```json
{
  "name": "Proveedor de ejemplo",
  "country": "USA",
  "categories": ["warehouse_supplies"],
  "rate_per_shipment": 1.25,
  "currency": "USD",
  "status": "active"
}
```

→ 201:

```json
{
  "name": "Proveedor de ejemplo",
  "country": "USA",
  "categories": ["warehouse_supplies"],
  "rate_per_shipment": 1.25,
  "currency": "USD",
  "status": "active",
  "service_zone": null,
  "contact_email": null,
  "notes": null,
  "id": 16,
  "updated_at": "2026-09-27T23:07:06.389797Z"
}
```

El mismo cuerpo con `"rate_per_shipment": 0` → 422 (formato de validación de FastAPI):

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": ["body", "rate_per_shipment"],
      "msg": "Input should be greater than 0",
      "input": 0,
      "ctx": { "gt": 0.0 }
    }
  ]
}
```

Otros 422: `status` fuera de `active`/`suspended`, país o categoría inexistentes, `categories` vacía, email sin
formato, campo obligatorio ausente (`Field required`) o moneda que no corresponde al país
(`Un proveedor de USA debe usar la moneda USD (recibido: EUR)`).

### `PATCH /suppliers/{id}/rate`

`PATCH /suppliers/11/rate` con `{"rate_per_shipment": 4.75}` → 200 con Nacex a 4.75 y `updated_at` nuevo
(`2026-09-27T22:34:26.591298Z` → `2026-09-27T23:07:06.419958Z`). `0` o negativos → 422 y la tarifa no cambia.

### `PATCH /suppliers/{id}/status`

`PATCH /suppliers/5/status` con `{"status": "active"}` → 200 con Laser Ship reactivado (su `updated_at` no cambia).
`{"status": "inactive"}` → 422 `Input should be 'active' or 'suspended'`.

### `DELETE /suppliers/{id}`

`DELETE /suppliers/16` → 204 sin cuerpo; repetirlo → 404. El flujo habitual de TrackFlow es **suspender, no
eliminar**: por eso el backoffice no ofrece borrar.

### Desde PowerShell 5.1

Además de Swagger UI (`/docs`):

```powershell
(Invoke-RestMethod "http://localhost:8000/suppliers?country=Spain&category=carrier_last_mile") | Format-Table id, name, rate_per_shipment, currency, status
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/suppliers/1/rate" -ContentType "application/json" -Body '{"rate_per_shipment": 7.99}'
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/suppliers/1/status" -ContentType "application/json" -Body '{"status": "suspended"}'
curl.exe -s "http://localhost:8000/suppliers?category=carrier_international"
```

- Los paréntesis del primer comando hacen falta: sin ellos, PowerShell 5.1 trata la lista JSON como un único objeto.
- En PowerShell, `curl` es un alias de `Invoke-WebRequest`: usa `curl.exe`. Para enviar cuerpos con acentos usa
  Swagger UI o `curl.exe --data-binary "@cuerpo.json"` (como argumento, Windows los envía mal codificados y la API
  responde 400).

## Analizador de incidencias

Endpoints en [`app/routes/incidents.py`](./app/routes/incidents.py); validación, métricas y exportación en
[`packages/analisis-incidencias`](../../packages/analisis-incidencias/README.md) (la misma lógica que
`scripts/analyze.py`). Contexto: [`CONTEXT-incidencias.es.md`](../../CONTEXT-incidencias.es.md). Documentación completa
(reglas, métricas, formato del CSV y decisiones): [`docs/analizador-incidencias.md`](../../docs/analizador-incidencias.md).

| Método y ruta | Éxito | Errores |
| --- | --- | --- |
| `POST /api/incidents/analyze` | 200 + métricas en JSON (`multipart/form-data`, CSV en el campo `file`) | 400 sin fichero · 413 > 5 MB · 415 no `.csv` · 422 contenido no procesable · 500 genérico |
| `GET /api/incidents/results/export` | 200 + `results.csv` (`text/csv; charset=utf-8`, `attachment`) | 404 sin análisis previo · 500 genérico |

- Prefijo `/api` porque así lo pide el ejercicio (proveedores usa `/suppliers` sin prefijo).
- El último análisis correcto se guarda **en memoria** (`app.state.ultimo_analisis`): se pierde al reiniciar y exige
  un solo proceso (un worker). Un análisis fallido no lo sustituye.
- Los errores inesperados se capturan solo en este router: al cliente le llega `{"detail": "Error interno del
  servidor."}` y la traza queda en el log. Proveedores no cambia.
- El log (`trackflow.api.incidents`) registra una línea de resumen por análisis, sin correos:
  `Análisis de 'incidents-trackflow.csv': 100 registros (95 válidos, 5 inválidos)`.

Desde PowerShell 5.1, con el CSV de prueba (desde `services\api`):

```powershell
curl.exe -s -F "file=@..\..\scripts\incidents-trackflow.csv" http://localhost:8000/api/incidents/analyze
curl.exe -s -o results.csv http://localhost:8000/api/incidents/results/export
```

El `results.csv` descargado es idéntico byte a byte al que exporta `python analyze.py`. También se pueden probar desde
Swagger UI (`/docs`, botón “Try it out” y selector de fichero).

## Tests

```powershell
uv run pytest -q
```

144 tests con pytest y `TestClient`: 118 del directorio de proveedores (cada uno sobre una base TinyDB temporal; nunca
tocan `db/suppliers.json`) y 26 del analizador de incidencias:

| Fichero | Qué cubre |
| --- | --- |
| [`tests/test_models.py`](./tests/test_models.py) | Proveedor válido, obligatorios, estados, países, categorías, tarifa 0/negativa/texto/booleano, moneda por país, email, campos del servidor |
| [`tests/test_database.py`](./tests/test_database.py) | Ruta, ids, UTF-8, reapertura, lectura desde otro proceso, escrituras concurrentes |
| [`tests/test_seed.py`](./tests/test_seed.py) | Seed idéntico al CONTEXT, 1.ª y 2.ª ejecución, inserción parcial, no sobrescribe, salida por consola |
| [`tests/test_api.py`](./tests/test_api.py) | Los 6 endpoints: 201/200/204, filtros y combinación, 404, 422, `updated_at`, persistencia al reiniciar (otro proceso), CORS, UTF-8 |
| [`tests/test_incidents.py`](./tests/test_incidents.py) | Valores esperados del CONTEXT, equivalencia con el script y exportación idéntica byte a byte, 400/404/413/415/422/500, último análisis, sin correos en JSON/log/exportación, CORS y `Content-Disposition` expuesto |

## Persistencia

Los datos se guardan con **TinyDB** en un fichero JSON en disco, así que sobreviven a los reinicios de la API:

| | |
| --- | --- |
| Ruta por defecto | `services/api/db/suppliers.json` (la carpeta se crea sola) |
| Tabla | `suppliers` (el `id` de cada proveedor es el `doc_id` que asigna TinyDB) |
| Cambiar la ruta | variable de entorno `SUPPLIERS_DB_PATH` (los tests usan un fichero temporal) |
| Git | `db/` está en `.gitignore`: la base local no se versiona |

El acceso está en [`app/database.py`](./app/database.py): cada uso abre el fichero, trabaja con la tabla y lo cierra
(lee siempre el estado del disco), con un candado para que las peticiones concurrentes no corrompan el JSON.

## Estructura

```text
services/api/
├── pyproject.toml        # dependencias (incl. ../../packages/analisis-incidencias), script `seed`, entrypoint
├── uv.lock
├── app/
│   ├── main.py           # FastAPI, CORS, JSON UTF-8, logger `trackflow`, /health
│   ├── models.py         # modelos Pydantic y valores válidos del CONTEXT
│   ├── database.py       # TinyDB
│   ├── seed.py           # `uv run seed`
│   └── routes/
│       ├── suppliers.py  # /suppliers
│       └── incidents.py  # /api/incidents
├── tests/
└── db/                   # base local (ignorada en git)
```

## Capturas

Tomadas por el desarrollador en local (carpeta [`screenshots/`](./screenshots/)):

- Seeder, dos ejecuciones seguidas (15/0/15 y 0/15/15): [`screenshot seeder.png`](./screenshots/screenshot%20seeder.png)
- `GET /suppliers?country=Spain` en Swagger UI (200, 6 proveedores): [parte 1](./screenshots/screenshot%20endpoint%20filtro%20pais1.png),
  [parte 2](./screenshots/screenshot%20endpoint%20filtro%20pais2.png),
  [parte 3](./screenshots/screenshot%20endpoint%20filtro%20pais3.png)

- `POST /api/incidents/analyze` en Swagger UI con el CSV de prueba (200, `access-control-expose-headers:
  Content-Disposition`): [`screenshot incidencias analyze.png`](./screenshots/screenshot%20incidencias%20analyze.png)

Las del backoffice (proveedores con filtros y análisis de incidencias) están en
[`uis/backoffice/screenshots/`](../../uis/backoffice/screenshots/).

## Limitaciones conocidas

- Sin autenticación: solo para uso local (ver aviso al principio).
- Si se borra el proveedor con el `id` más alto, TinyDB reutiliza ese `id` en el siguiente alta (calcula el siguiente
  como máximo + 1).
- Un único `updated_at` por proveedor (última actualización de tarifa): no se guarda el histórico de tarifas
  anteriores.
- El seeder y la API no se coordinan entre procesos (ver la nota del seeder).
- El último análisis de incidencias vive en memoria: se pierde al reiniciar, es compartido por todos los usuarios y con
  varios workers la exportación podría no encontrarlo.
