# TrackFlow API — Directorio de proveedores, analizador y gestor de incidencias

API de TrackFlow con tres módulos, protegidos con autenticación JWT:

- **Directorio de proveedores** (`/suppliers`): el registro centralizado que sustituye a las hojas de cálculo de Carlos
  Vega (Carrier Operations) y Ana Whitfield (Warehouse Operations) y unifica los mercados de USA y España. Fuente de
  verdad de campos, categorías, estados y datos iniciales: [`CONTEXT-directorio.md`](../../CONTEXT-directorio.md).
- **Analizador de incidencias** (`/api/incidents`): valida el CSV de incidencias de CX y calcula sus métricas con el
  paquete compartido [`packages/analisis-incidencias`](../../packages/analisis-incidencias/README.md). Ver
  [Analizador de incidencias](#analizador-de-incidencias).
- **Gestor de incidencias** (también en `/api/incidents`): registro, listado con filtros, cambio de estado y resumen
  de las incidencias de TrackFlow, con el CSV del analizador como datos iniciales. Fuente de verdad:
  [`CONTEXT-gestor-incidencias.es.md`](../../CONTEXT-gestor-incidencias.es.md). Ver
  [Gestor de incidencias](#gestor-de-incidencias).
- **Autenticación** (`/auth`, `/users`, `/profiles`): usuarios y perfiles en TinyDB, login con JWT Bearer y protección
  de rutas. Ver [Autenticación](#autenticación) y la documentación completa en
  [`docs/autenticacion.md`](../../docs/autenticacion.md).

**Stack:** Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), FastAPI, Pydantic y TinyDB (base de datos en un fichero
JSON). Sin ORM, Docker ni base de datos de servidor: TinyDB es una elección deliberada de este ejercicio. La consumen
las páginas `/proveedores`, `/incidencias` y `/gestor-incidencias` del [backoffice](../../uis/backoffice/README.md).

> Todas las rutas de proveedores e incidencias exigen un token (`Authorization: Bearer`). Solo son públicas
> `POST /users`, `POST /auth/login`, `POST /auth/token` y `/health`. Hoy se usa en **local**. Antes de publicarla, lee
> los riesgos pendientes de [`docs/autenticacion.md`](../../docs/autenticacion.md#auditoría-de-seguridad) y las
> instrucciones (no ejecutadas) de [`docs/despliegue-api.md`](../../docs/despliegue-api.md).

## Instalación

Requiere `uv` (`uv --version`). Desde la raíz del repo, en Windows PowerShell (un comando por línea):

```powershell
cd services\api
uv sync
```

`uv sync` crea `.venv/` e instala las versiones exactas de `uv.lock` (FastAPI, Pydantic, TinyDB, uvicorn,
python-multipart, python-jose, libpass con bcrypt y el paquete local `analisis-incidencias` en modo editable; y
pytest + httpx2 para los tests).

## Ejecución

La primera vez, crea el `.env` (ignorado en git) y genera la clave de firma de los tokens. Pega la clave en
`SECRET_KEY=`:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Después:

```powershell
uv run seed
uv run --env-file .env create-admin tu.email@trackflow.test
uv run --env-file .env uvicorn app.main:app --reload --port 8000
```

- `create-admin` pide una contraseña y crea el primer administrador. Solo hace falta una vez.
- API: http://localhost:8000 · Swagger UI (botón **Authorize** con tu email y contraseña): http://localhost:8000/docs
- Comprobación rápida: http://localhost:8000/health → `{"status":"ok"}`
- Sin `SECRET_KEY` válida (falta, tiene menos de 32 caracteres o vale `change-me`) la API **no arranca** y explica
  cómo generarla. Tampoco arranca con un `REGISTRATION_CODE` de menos de 12 caracteres.

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `SECRET_KEY` | — (**obligatoria**) | Clave de firma de los JWT, de al menos 32 caracteres |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Minutos de validez de cada token |
| `REGISTRATION_CODE` | — (registro abierto) | Código de invitación que exige `POST /users` (≥ 12 caracteres). Mejora adicional de AUTH-02, fuera del enunciado ([detalle](../../docs/autenticacion.md#mejora-adicional-código-de-invitación-registration_code)). **Defínelo antes de publicar la API** |
| `AUTH_DB_PATH` | `services/api/db/auth.json` | Fichero de TinyDB de usuarios y perfiles |
| `SUPPLIERS_DB_PATH` | `services/api/db/suppliers.json` | Fichero de TinyDB de proveedores |
| `INCIDENTS_DB_PATH` | `services/api/db/incidents.json` | Fichero de TinyDB del gestor de incidencias |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3002,http://127.0.0.1:3002` | Orígenes del navegador autorizados (el backoffice). Admite la cabecera `Authorization` y expone `Content-Disposition` para las descargas |

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

## Autenticación

Resumen. El detalle (permisos, errores, verificación y auditoría) está en
[`docs/autenticacion.md`](../../docs/autenticacion.md).

- `User` (email, `hashed_password` con bcrypt, `is_active`, `role` = `admin` · `manager` · `user`, `created_at`) y
  `Profile` (`name`, `phone`, `address`), 1 a 1, **solo en TinyDB** (`db/auth.json`). Sin tablas en ninguna otra base
  de datos.
- JWT HS256 con `sub` (UUID del usuario en TinyDB), `iat` y `exp`. Sin sesiones ni cookies.
- La dependencia `get_current_user` ([`app/dependencies.py`](./app/dependencies.py)) valida el token y devuelve el
  usuario activo. Cualquier fallo es un 401; actuar sobre algo ajeno es un 403. Desde AUTH-03 también rechaza los
  tokens emitidos antes del último cambio de contraseña (`password_changed_at`).
- **Recuperación de contraseña (AUTH-03):** enlaces opacos de un solo uso (30 min, solo su SHA-256 en
  `db/auth.json`, tabla `password_reset_tokens`) enviados con [Resend](https://resend.com) desde
  [`app/services/email.py`](./app/services/email.py). Variables: `RESEND_API_KEY` (sin ella no se envían emails),
  `MAIL_FROM` **entre comillas dobles** en el `.env` (`MAIL_FROM="TrackFlow <no-reply@tu-dominio>"`, dominio verificado
  en Resend), `FRONTEND_BASE_URL` (por defecto `http://localhost:3002`) y `RESET_TOKEN_EXPIRE_MINUTES` (15–60, 30 por
  defecto). Los tests nunca envían emails. **Si cambias el `.env`, para la API (`Ctrl+C`) y vuelve a arrancarla:**
  `--reload` recarga el código, pero no las variables. Comprueba también que no queden dos APIs arrancadas: la antigua
  seguiría ocupando el puerto 8000. Al pedir un enlace, la consola debe mostrar
  `trackflow.email: Email password_reset … enviado (id …)`.

| Método y ruta | Acceso |
| --- | --- |
| `POST /users` | pública: registro, siempre con rol `user`; con `REGISTRATION_CODE`, exige `invitation_code` (si no, 403) |
| `POST /auth/login` · `POST /auth/token` | pública: JSON `{email, password}` · formulario OAuth2 de Swagger |
| `GET /auth/me` | Bearer: email, rol y perfil |
| `POST /auth/forgot-password` | pública: siempre 200 con el mismo mensaje; si el email es de un usuario activo, envía el enlace por email (AUTH-03) |
| `POST /auth/reset-password` | pública: `{token, new_password}`; enlace de un solo uso (400 si no vale); cierra todas las sesiones (AUTH-03) |
| `POST /auth/change-password` | Bearer: `{current_password, new_password}` (400 si la actual no es correcta); devuelve un token nuevo y cierra las demás sesiones (AUTH-03) |
| `GET /users` · `GET /users/{id}` | Bearer: `admin`/`manager`, o el propio usuario en `/{id}` |
| `PUT /users/{id}` | Bearer: email, el propio usuario y con `current_password`; `role` e `is_active`, solo `admin`. Sin `password` (422): se cambia con `/auth/change-password` |
| `DELETE /users/{id}` | Bearer: el propio usuario o `admin` (borra también el perfil) |
| `GET /profiles/me` · `PUT /profiles/me` | Bearer: solo el propio perfil |
| Las 6 rutas de `/suppliers` y las 7 de `/api/incidents` (2 del analizador y 5 del gestor) | Bearer: cualquier usuario autenticado |
| `GET /health` | pública |

Desde PowerShell 5.1:

```powershell
$login = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/auth/login" -ContentType "application/json" -Body '{"email": "tu.email@trackflow.test", "password": "tu-contraseña"}'
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "http://localhost:8000/auth/me" -Headers $h
```

Los ejemplos de proveedores e incidencias de más abajo usan esa variable `$h`.

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
**Todos exigen `Authorization: Bearer <token>`**: sin él, o con un token no válido o caducado → 401.

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

Además de Swagger UI (`/docs`), con el `$h` de [Autenticación](#autenticación):

```powershell
(Invoke-RestMethod "http://localhost:8000/suppliers?country=Spain&category=carrier_last_mile" -Headers $h) | Format-Table id, name, rate_per_shipment, currency, status
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/suppliers/1/rate" -Headers $h -ContentType "application/json" -Body '{"rate_per_shipment": 7.99}'
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/suppliers/1/status" -Headers $h -ContentType "application/json" -Body '{"status": "suspended"}'
curl.exe -s -H "Authorization: Bearer $($login.access_token)" "http://localhost:8000/suppliers?category=carrier_international"
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

- Ambos exigen `Authorization: Bearer <token>` (401 sin él).
- Prefijo `/api` porque así lo pide el ejercicio (proveedores usa `/suppliers` sin prefijo).
- El último análisis correcto se guarda **en memoria** (`app.state.ultimo_analisis`): se pierde al reiniciar y exige
  un solo proceso (un worker). Un análisis fallido no lo sustituye.
- Los errores inesperados se capturan solo en este router: al cliente le llega `{"detail": "Error interno del
  servidor."}` y la traza queda en el log. Proveedores no cambia.
- El log (`trackflow.api.incidents`) registra una línea de resumen por análisis, sin correos:
  `Análisis de 'incidents-trackflow.csv': 100 registros (95 válidos, 5 inválidos)`.

Desde PowerShell 5.1, con el CSV de prueba (desde `services\api`):

```powershell
curl.exe -s -H "Authorization: Bearer $($login.access_token)" -F "file=@..\..\scripts\incidents-trackflow.csv" http://localhost:8000/api/incidents/analyze
curl.exe -s -H "Authorization: Bearer $($login.access_token)" -o results.csv http://localhost:8000/api/incidents/results/export
```

El `results.csv` descargado es idéntico byte a byte al que exporta `python analyze.py`. También se pueden probar desde
Swagger UI (`/docs`, botón “Try it out” y selector de fichero).

## Gestor de incidencias

Endpoints en [`app/routes/incident_manager.py`](./app/routes/incident_manager.py), modelos en
[`app/incident_models.py`](./app/incident_models.py) y acceso a TinyDB en
[`app/services/incidents.py`](./app/services/incidents.py). Los valores permitidos, la validación y las transiciones
vienen de `gestor.py`, en [`packages/analisis-incidencias`](../../packages/analisis-incidencias/README.md). Documentación
completa (modelo, seed, errores, backoffice y limitaciones): [`docs/gestor-incidencias.md`](../../docs/gestor-incidencias.md).

| Método y ruta | Éxito | Errores |
| --- | --- | --- |
| `POST /api/incidents` | 201 + incidencia creada, en estado `open` | 400 datos no válidos |
| `GET /api/incidents` | 200 + lista, de la más reciente a la más antigua (filtros opcionales `status`, `origin`, `branch`, `category`); `[]` sin datos | 400 valor de filtro que no existe |
| `GET /api/incidents/summary` | 200 + totales por estado, categoría, origen y sede (a 0 sin datos) | — |
| `GET /api/incidents/{id}` | 200 + incidencia | 404 · 400 id no numérico |
| `PATCH /api/incidents/{id}/status` | 200 + incidencia con el nuevo estado y `updated_at` renovado | 400 transición no permitida o estado desconocido · 404 |

- Todos exigen `Authorization: Bearer <token>` (401 sin él).
- Campos que envía el cliente, todos obligatorios: `title` (máx. 120), `description` (máx. 2.000), `category`,
  `origin` y `branch`. `id`, `status`, `created_at` y `updated_at` los pone el servidor.
- Transiciones: `open → in_progress | discarded` e `in_progress → resolved | discarded`. `resolved` y `discarded` son
  finales.
- **Errores propios de este router.** Los datos no válidos responden **400** (no el 422 del resto de la API) con un
  elemento por campo y el mensaje en español, sin devolver el valor recibido:
  `{"detail": [{"field": "description", "loc": ["body", "description"], "msg": "La descripción es obligatoria."}]}`.
  Un error inesperado responde 500 `{"detail": "Error interno del servidor."}` y la traza queda en el log.
- Además, `app/main.py` convierte cualquier error no controlado de **cualquier** ruta en ese mismo 500 genérico.

### Seed del CSV histórico

Desde la **raíz del repo**, con la API parada:

```powershell
uv run --project services/api python scripts/seed_incidents.py
```

Carga las 95 filas válidas de `scripts/incidents-trackflow.csv` (descarta e informa de 5), con `origin = customer`. Es
idempotente: la segunda ejecución da 0 insertadas y 95 duplicadas. Tras el seed, `GET /api/incidents/summary` devuelve
29 `open`, 52 `resolved` y 14 `discarded`; y 14 `lost_parcel`, 45 `carrier_issue`, 19 `delivery_failure` y 17
`returns_issue`, los valores esperados del CONTEXT. Para empezar de cero, borra `db\incidents.json` y repítelo.

## Tests

```powershell
uv run pytest -q
```

751 tests con pytest y `TestClient`: 278 del gestor de incidencias, 118 del directorio de proveedores (cada uno sobre una base TinyDB temporal; nunca
tocan `db/suppliers.json`), 26 del analizador de incidencias, 145 de autenticación y 184 de recuperación y cambio de
contraseña (AUTH-03). No hace falta `.env`: [`tests/conftest.py`](./tests/conftest.py) pone una `SECRET_KEY` de pruebas
y una base de usuarios temporal en cada test, borra las variables de email (ningún test envía emails de verdad) y el
fixture `client` va autenticado. Así los tests anteriores comprueban que las rutas protegidas siguen
funcionando con un token válido.

| Fichero | Qué cubre |
| --- | --- |
| [`tests/test_models.py`](./tests/test_models.py) | Proveedor válido, obligatorios, estados, países, categorías, tarifa 0/negativa/texto/booleano, moneda por país, email, campos del servidor |
| [`tests/test_database.py`](./tests/test_database.py) | Ruta, ids, UTF-8, reapertura, lectura desde otro proceso, escrituras concurrentes |
| [`tests/test_seed.py`](./tests/test_seed.py) | Seed idéntico al CONTEXT, 1.ª y 2.ª ejecución, inserción parcial, no sobrescribe, salida por consola |
| [`tests/test_api.py`](./tests/test_api.py) | Los 6 endpoints: 201/200/204, filtros y combinación, 404, 422, `updated_at`, persistencia al reiniciar (otro proceso), CORS, UTF-8 |
| [`tests/test_incidents.py`](./tests/test_incidents.py) | Valores esperados del CONTEXT, equivalencia con el script y exportación idéntica byte a byte, 400/404/413/415/422/500, último análisis, sin correos en JSON/log/exportación, CORS y `Content-Disposition` expuesto |
| [`tests/test_incident_models.py`](./tests/test_incident_models.py) | Gestor: modelos, campos obligatorios, valores permitidos, fechas, tabla TinyDB y datos inválidos que no llegan a la base |
| [`tests/test_seed_incidents.py`](./tests/test_seed_incidents.py) | Gestor: `scripts/seed_incidents.py` con los totales del CONTEXT, idempotencia, inválidas reportadas, sin correos y errores de fichero |
| [`tests/test_incident_manager.py`](./tests/test_incident_manager.py) | Gestor: los 5 endpoints, 400 por campo, filtros, 404, las 16 combinaciones de transición, resumen con y sin datos, 401, 500 sin traza y convivencia con el analizador y proveedores |
| [`tests/test_auth.py`](./tests/test_auth.py) | Usuarios y perfiles en TinyDB, bcrypt, roles, login, JWT (válido, malformado, caducado, otra firma, `alg: none`, sin claims, usuario borrado o desactivado), configuración, código de invitación (`REGISTRATION_CODE`), 401/403/404/409, ownership, las 8 rutas existentes protegidas, `create-admin` |
| [`tests/test_password_reset.py`](./tests/test_password_reset.py) | AUTH-03: enlaces (solo hash, caducidad, un solo uso, concurrencia, límite de 60 s, limpieza), `forgot-password` (misma respuesta exista o no el email), `reset-password` (tokens no válidos, cierre de sesiones), `change-password` y cambio de email con contraseña |
| [`tests/test_email.py`](./tests/test_email.py) | AUTH-03: configuración de Resend y `MAIL_FROM`, petición exacta a la API de Resend, errores del proveedor, logs sin datos sensibles y plantilla del email |

## Persistencia

Los datos se guardan con **TinyDB** en un fichero JSON en disco, así que sobreviven a los reinicios de la API:

| | |
| --- | --- |
| Ruta por defecto | `services/api/db/suppliers.json` (la carpeta se crea sola) |
| Tabla | `suppliers` (el `id` de cada proveedor es el `doc_id` que asigna TinyDB) |
| Cambiar la ruta | variable de entorno `SUPPLIERS_DB_PATH` (los tests usan un fichero temporal) |
| Usuarios y perfiles | `services/api/db/auth.json`, tablas `users` y `profiles` (el `id` es un UUID); variable `AUTH_DB_PATH` |
| Incidencias del gestor | `services/api/db/incidents.json`, tabla `incidents` (el `id` es el `doc_id`); variable `INCIDENTS_DB_PATH` |
| Git | `db/` está en `.gitignore`: la base local no se versiona |

El acceso está en [`app/database.py`](./app/database.py): cada uso abre el fichero, trabaja con la tabla y lo cierra
(lee siempre el estado del disco), con un candado para que las peticiones concurrentes no corrompan el JSON.

## Estructura

```text
services/api/
├── pyproject.toml        # dependencias (incl. ../../packages/analisis-incidencias), scripts `seed` y `create-admin`
├── uv.lock
├── .env.example          # SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REGISTRATION_CODE, RESEND_API_KEY, MAIL_FROM… (copiar a .env, ignorado)
├── app/
│   ├── main.py           # FastAPI, CORS, JSON UTF-8, logger `trackflow`, /health, comprobación de SECRET_KEY
│   ├── models.py         # modelos Pydantic de proveedores y valores válidos del CONTEXT
│   ├── incident_models.py  # modelos del gestor de incidencias (valores y reglas del paquete compartido)
│   ├── auth_models.py    # User, Profile, Role, PasswordResetToken y schemas de entrada/salida de autenticación
│   ├── security.py       # bcrypt, JWT, código de invitación y enlaces de recuperación (configuración desde el entorno)
│   ├── email_templates.py  # email de recuperación de contraseña (HTML + texto)
│   ├── dependencies.py   # OAuth2PasswordBearer + get_current_user
│   ├── database.py       # TinyDB (proveedores, usuarios e incidencias)
│   ├── seed.py           # `uv run seed`
│   ├── create_admin.py   # `uv run create-admin <email>`
│   ├── services/         # users.py, profiles.py (CRUD en TinyDB), password_reset.py (enlaces), email.py (Resend),
│   │                     # incidents.py (gestor de incidencias)
│   └── routes/
│       ├── auth.py       # /auth
│       ├── users.py      # /users
│       ├── profiles.py   # /profiles
│       ├── suppliers.py  # /suppliers
│       ├── incidents.py  # /api/incidents (analizador: /analyze y /results/export)
│       └── incident_manager.py  # /api/incidents (gestor: alta, listado, detalle, estado y resumen)
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

- Autenticación: el registro es público salvo que se defina `REGISTRATION_CODE`, y cualquier usuario autenticado
  puede operar proveedores e incidencias; sin límite de intentos de login ni *refresh tokens* (ver riesgos en
  [`docs/autenticacion.md`](../../docs/autenticacion.md)).
- Si se borra el proveedor con el `id` más alto, TinyDB reutiliza ese `id` en el siguiente alta (calcula el siguiente
  como máximo + 1).
- Un único `updated_at` por proveedor (última actualización de tarifa): no se guarda el histórico de tarifas
  anteriores.
- El seeder y la API no se coordinan entre procesos (ver la nota del seeder).
- Gestor de incidencias: sin paginación, edición ni borrado; sin permisos por rol; la integridad la da el modelo
  Pydantic, no TinyDB (ver [`docs/gestor-incidencias.md`](../../docs/gestor-incidencias.md#limitaciones)).
- El último análisis de incidencias vive en memoria: se pierde al reiniciar, es compartido por todos los usuarios y con
  varios workers la exportación podría no encontrarlo.
