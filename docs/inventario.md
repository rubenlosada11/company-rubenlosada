# Gestión de inventario backend — Hito 5 (TrackFlow)

API de inventario unificada para los SKUs de los almacenes de **Los Ángeles (`LA`)** y **Zaragoza (`ZGZ`)** (ticket
Linear TRK-0341 de Andrés Kim, CTO). Registra cada unidad que entra (recepción de mercancía de una marca cliente) y
que sale (despacho a un cliente o pérdida confirmada). El stock **nunca se guarda**: se calcula siempre como entradas
menos salidas, y por almacén. Fuente de verdad de entidades, campos, rutas, reglas y datos semilla:
[`CONTEXT-gestor-inventario.es.md`](../CONTEXT-gestor-inventario.es.md).

Es el **Hito 5** del proyecto (ver [`hitos.md`](./hitos.md)). Solo backend: vive en la API existente
([`services/api`](../services/api/README.md)), con su autenticación JWT de TinyDB. No hay página en el backoffice.

## Arquitectura

El briefing describe una estructura genérica (`services/main.py`, `database.py`, `models.py`, `schemas.py`,
`routers/inventory.py`). En este monorepo la API ya existe en `services/api/app/` con sus propias convenciones, así que
el inventario se integra en ella (crear una segunda app FastAPI duplicaría la autenticación y es un cambio de
arquitectura que requiere confirmación, según `AGENTS.md`):

| Briefing | Este repo | Contenido |
| --- | --- | --- |
| `services/main.py` | [`services/api/app/main.py`](../services/api/app/main.py) | Registra `inventory.router` junto a los demás |
| `services/database.py` | [`services/api/app/database.py`](../services/api/app/database.py) | Clientes TinyDB (ya existían) + motor SQLModel (`get_engine`) + dependencia `get_db` |
| `services/models.py` | [`services/api/app/inventory_models.py`](../services/api/app/inventory_models.py) | Tablas SQLModel `SKU`, `StockEntry`, `StockExit`. `app/models.py` ya era el de proveedores; el nombre sigue el patrón `auth_models.py` / `incident_models.py` |
| `services/schemas.py` | [`services/api/app/inventory_schemas.py`](../services/api/app/inventory_schemas.py) | Schemas Pydantic de petición y respuesta |
| `services/routers/inventory.py` | [`services/api/app/routes/inventory.py`](../services/api/app/routes/inventory.py) | `APIRouter(prefix="/inventory")`. La carpeta de routers del repo es `routes/` |
| — | [`services/api/app/services/inventory.py`](../services/api/app/services/inventory.py) | Reglas de negocio y cálculo del stock (capa de servicio del repo; la usan la API y el seed) |
| — | [`services/api/app/seed_inventory.py`](../services/api/app/seed_inventory.py) | Datos semilla: `uv run seed-inventory` |

```text
Petición ─► routes/inventory.py ─► services/inventory.py ─► SQLModel (SKU, StockEntry, StockExit) ─► SQLite / PostgreSQL
              │ get_current_user (JWT)      │ stock = Σ entradas − Σ salidas, por almacén
              └─ user_uuid = usuario de TinyDB (db/auth.json)
```

## Base de datos

- **ORM:** SQLModel (SQLAlchemy 2) — única dependencia nueva de la API.
- **Desarrollo local (por defecto):** SQLite en `services/api/db/inventory.db` (carpeta ignorada en git). Las tablas se
  crean solas la primera vez que se usa el inventario (`SQLModel.metadata.create_all`), sin migraciones.
- **Supabase / PostgreSQL:** se define `DATABASE_URL` con la cadena de conexión de Supabase. No se ha conectado a
  ningún proyecto de Supabase (no hay credenciales en el repo) ni se ha instalado el driver; ver
  [Conectar Supabase](#conectar-supabase-pendiente).
- **Usuarios:** no hay tabla ni modelo `User` en SQL (regla 4). `user_uuid` es el UUID del usuario en TinyDB, el `sub`
  del JWT, sin clave foránea (vive en otra base).

| Tabla | Modelo | Campos |
| --- | --- | --- |
| `skus` | `SKU` | `id`, `name`, `sku` (único), `client_name`, `category`, `warehouse` |
| `stock_entries` | `StockEntry` | `id`, `sku_id` (FK → `skus.id`), `quantity`, `reference`, `warehouse`, `created_at`, `user_uuid` |
| `stock_exits` | `StockExit` | `id`, `sku_id` (FK → `skus.id`), `quantity`, `exit_type`, `tracking_number`, `warehouse`, `created_at`, `user_uuid` |

`current_stock` no es una columna: solo existe en el schema de respuesta (`SKURead`).

## Endpoints

Todos bajo `/inventory` y con `Authorization: Bearer <token>` (sin token → 401). Documentación interactiva en
`http://localhost:8000/docs` (etiqueta **inventory**).

| Método | Ruta | Respuesta | Errores |
| --- | --- | --- | --- |
| `GET` | `/inventory/products` | 200, lista de `SKURead` por `id`. Filtro opcional `?warehouse=LA\|ZGZ` (SKUs registrados en ese almacén) | 422 almacén no válido |
| `POST` | `/inventory/products` | 201, `SKURead` con stock 0 | 409 código repetido · 422 datos no válidos |
| `GET` | `/inventory/products/{id}` | 200, `SKURead` | 404 · 422 id no entero |
| `POST` | `/inventory/orders/inbound` | 201, `StockEntryRead` | 404 SKU inexistente · 422 |
| `POST` | `/inventory/orders/outbound` | 201, `StockExitRead` | 400 stock insuficiente · 404 · 422 (p. ej. `dispatch` sin `tracking_number`) |
| `GET` | `/inventory/orders` | 200, entradas y salidas con los datos del SKU, de la más reciente a la más antigua. Filtros opcionales `?warehouse=` y `?sku_id=` | 422 filtro no válido |

### Cuerpos de petición

```json
POST /inventory/products
{ "name": "Zapatilla blanca clásica - Talla 42", "sku": "CLT-SNK-W-42", "client_name": "PureStep Footwear",
  "category": "fashion", "warehouse": "LA" }

POST /inventory/orders/inbound
{ "sku_id": 1, "quantity": 40, "reference": "PO-2024-0098", "warehouse": "LA" }

POST /inventory/orders/outbound
{ "sku_id": 1, "quantity": 12, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456784", "warehouse": "LA" }
{ "sku_id": 4, "quantity": 3, "exit_type": "loss", "tracking_number": null, "warehouse": "ZGZ" }
```

- `id`, `created_at` y `user_uuid` los pone el servidor; si llegan en el cuerpo se ignoran. `user_uuid` es siempre el
  del usuario del token: nadie puede registrar un movimiento en nombre de otro.
- `warehouse` es opcional en los movimientos: si no se envía, se usa el almacén del SKU.
- Los textos se recortan (espacios al principio y al final) y no pueden quedar vacíos. Límites técnicos: `name` 200,
  `client_name` 120, `sku`, `reference` y `tracking_number` 64 caracteres.
- `quantity` es un entero estricto mayor que 0 (se rechazan `"5"`, `5.0`, `true`) y como máximo 2.147.483.647
  (`INTEGER` de PostgreSQL).
- `category`: `fashion` · `electronics` · `cosmetics`. `warehouse`: `LA` · `ZGZ`. `exit_type`: `dispatch` · `loss`.
  Valores exactos (sensibles a mayúsculas).

### Respuestas

```json
SKURead
{ "id": 1, "name": "Zapatilla blanca clásica - Talla 42", "sku": "CLT-SNK-W-42", "client_name": "PureStep Footwear",
  "category": "fashion", "warehouse": "LA", "current_stock": 53, "stock_by_warehouse": { "LA": 53, "ZGZ": 0 } }

Movimiento de GET /inventory/orders (StockEntryRead / StockExitRead + movement_type + sku)
{ "id": 1, "sku_id": 1, "quantity": 12, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456784",
  "warehouse": "LA", "created_at": "2026-10-31T14:19:07.436635Z", "user_uuid": "291a43ea-…",
  "movement_type": "outbound",
  "sku": { "id": 1, "name": "Zapatilla blanca clásica - Talla 42", "sku": "CLT-SNK-W-42",
           "client_name": "PureStep Footwear", "category": "fashion", "warehouse": "LA" } }
```

Las entradas y las salidas tienen numeración propia (`id` 1 puede ser una entrada y una salida): `movement_type`
(`inbound` | `outbound`) las distingue. `created_at` va siempre en UTC (`Z`).

## Reglas de negocio

| # | Regla del briefing | Implementación |
| --- | --- | --- |
| 1 | `current_stock` siempre se calcula | Dos consultas agregadas (`SUM` agrupado por SKU y almacén) sobre entradas y salidas; ninguna columna de stock. Un test comprueba que la tabla no tiene `current_stock` |
| 2 | Ninguna salida puede dejar el stock por debajo de cero → 400 `"Insufficient stock for SKU '{sku}'. Available: {available}, requested: {quantity}."` | Se comprueba **antes de escribir**, con el stock del almacén de la salida. Mensaje literal (en inglés, como lo pide el briefing). Comprobar y escribir es una sola operación bajo un candado (y `SELECT … FOR UPDATE` del SKU en PostgreSQL): dos salidas simultáneas no pueden gastar el mismo stock |
| 3 | `tracking_number` obligatorio en `dispatch` y nulo en `loss` | Validación del schema `StockExitCreate` → 422 en el campo `tracking_number`. Un texto vacío cuenta como nulo |
| 4 | Sin tabla de usuarios en SQL | `user_uuid` = UUID del usuario de TinyDB que hace la petición |
| 5 | Los dos almacenes en las mismas tablas | `warehouse` en `SKU`, `StockEntry` y `StockExit` y en todas sus respuestas |
| 6 | Stock por SKU **y por almacén**, nunca agregado | Ver la decisión siguiente |

### Decisión: stock por almacén (regla 6)

Un SKU se registra en un almacén (`SKU.warehouse`), pero cada movimiento lleva su propio `warehouse`, así que un mismo
SKU puede tener stock en los dos almacenes (el ejemplo del briefing: 20 unidades en LA y 15 en ZGZ). La API **nunca
suma** las cifras de LA y ZGZ:

- `current_stock` = stock del SKU **en su almacén** (`warehouse` del SKU): entradas − salidas registradas allí.
- `stock_by_warehouse` = desglose `{"LA": n, "ZGZ": m}`, con las dos cifras por separado.
- El listado (`GET /inventory/products`) usa los mismos dos campos: **se muestra el desglose por almacén, no un total**
  (la elección que el briefing pide documentar).
- Una salida se comprueba contra el stock de **su** almacén: con 20 en LA y 15 en ZGZ, una salida de 16 en ZGZ es un 400
  (`Available: 15`) aunque el total sea 35.

Los datos semilla siguen el modelo del briefing: el mismo producto en dos almacenes son dos SKUs (`CLT-SNK-W-42` en LA
y `CLT-SNK-W-42-Z` en ZGZ) y cada movimiento va al almacén de su SKU.

### Otras decisiones

| Decisión | Motivo |
| --- | --- |
| Código `sku` único (sin distinguir mayúsculas) → 409 | El mensaje de la regla 2 identifica el SKU solo por su código; con códigos repetidos sería ambiguo. Índice único en la base contra altas simultáneas |
| SKU inexistente en un movimiento → 404 (antes de comprobar el stock) | Mismo mensaje que `GET /inventory/products/{id}` |
| `dispatch` sin `tracking_number` → 422 (no 400) | El briefing pide «un error de validación»: es la validación estándar de FastAPI, con el manejador común del repo (sin devolver el valor recibido) |
| Rutas protegidas con el JWT existente | «La autenticación se queda en TinyDB»; los datos de stock son internos, como proveedores e incidencias |
| Tablas creadas al primer uso, no al arrancar | Si la base del inventario no está disponible solo falla el inventario, no el resto de la API |
| Sin Alembic | Simplicidad: `create_all` basta para crear las tablas. Si el modelo cambia con datos reales, habrá que añadir migraciones |
| Movimientos de la API ordenados del más reciente al más antiguo | Uso habitual de un historial; en el mismo instante, las salidas primero y el `id` más alto antes |
| Errores en español salvo el de la regla 2 | Convención del repo; el de la regla 2 es literal del briefing |

## Datos semilla

```powershell
cd services\api
uv run seed-inventory
```

- Los **6 SKUs** de la tabla del briefing (un test comprueba que son idénticos), **7 entradas** (dos de `CLT-SNK-W-42`
  con 40 y 25 unidades; referencias `PO-2024-0098`, `GR-LA-0234`, … ; los dos almacenes) y **4 salidas** (dos
  `dispatch` con número de seguimiento, entre ellos `1Z999AA10123456784`, y dos `loss` con `tracking_number` nulo).
  Ninguna salida supera lo recibido en su almacén: pasan por la misma regla 2 que la API.
- Los movimientos se firman con un **usuario existente de TinyDB**: el primer administrador activo o el del email que
  se pase (`uv run seed-inventory operario@trackflow.test`). Sin usuarios, no carga nada y explica cómo crear el
  administrador (`uv run --env-file .env create-admin <email>`).
- **Idempotente:** solo inserta los SKUs que falten (por código) y solo carga los movimientos si no hay ninguno.

Stock resultante: `CLT-SNK-W-42` 53 (LA) · `CLT-SNK-W-42-Z` 28 (ZGZ) · `TEC-EAR-001` 52 (LA) · `CSM-SRM-030` 117 (ZGZ) ·
`CLT-CHN-N-32` 35 (LA) · `TEC-CHG-065` 50 (ZGZ).

## Notas de evaluación del briefing

| El evaluador… | Resultado | Test |
| --- | --- | --- |
| registra un `StockExit` que supera el stock del almacén | 400 con el mensaje literal, sin escribir nada | `test_exit_above_stock_returns_400_with_the_exact_message_and_writes_nothing`, `test_exit_is_checked_against_the_stock_of_its_own_warehouse` |
| intenta un `dispatch` sin `tracking_number` | 422 en el campo `tracking_number` | `test_dispatch_without_tracking_number_is_a_validation_error`, `test_dispatch_with_tracking_number_omitted_is_a_validation_error` |
| verifica que el stock es por almacén, no agregado | `current_stock` del almacén del SKU + `stock_by_warehouse` | `test_stock_is_per_warehouse_not_aggregated` |
| comprueba `warehouse` en los modelos y respuestas | Presente en las tres tablas y en todas las respuestas | `test_warehouse_is_present_in_every_response` |

## Pruebas

```powershell
cd services\api
uv run pytest tests/test_inventory.py tests/test_seed_inventory.py tests/test_inventory_database.py
```

116 tests (HTTP de los 6 endpoints, reglas 1–6, salidas simultáneas, base no disponible, seed y motor SQL), cada uno con su propia base
SQLite temporal (el `conftest.py` fija `DATABASE_URL`: nunca tocan `db/inventory.db` ni una base real). Cobertura de
líneas y ramas: 100 % en modelos, schemas, router y servicio; 95 % en el seed. Además se hicieron 8 pruebas de mutación
manuales (quitar el candado, `>` por `>=`, sumar los almacenes, quitar cada regla de `tracking_number`, tomar
`user_uuid` del cuerpo, quitar la autenticación): todas hacen fallar algún test.

## Conectar Supabase (pendiente)

No ejecutado: requiere un proyecto de Supabase y su contraseña, que no están en el repo (área de secretos).

1. Instalar el driver de PostgreSQL en la API: `uv add "psycopg[binary]"` (sin él, la API responde 500 en `/inventory`
   y el seed explica qué falta).
2. En `services/api/.env` (nunca en git): `DATABASE_URL="postgresql+psycopg://postgres.<proyecto>:<contraseña>@<host>:5432/postgres"`
   (cadena *Session pooler* de Supabase, entre comillas).
3. `uv run --env-file .env seed-inventory` crea las tablas y carga los datos.

## Limitaciones conocidas

- **Un solo worker.** El candado de la regla 2 protege los hilos de un proceso. En PostgreSQL, `SELECT … FOR UPDATE`
  bloquea además el SKU entre procesos; en SQLite con varios procesos no hay esa garantía.
- **Sin migraciones** (ver «Otras decisiones») ni paginación en los listados.
- **Permisos:** cualquier usuario autenticado puede registrar SKUs y movimientos, como en proveedores e incidencias. El
  briefing distingue operarios de almacén (entradas) y coordinadores logísticos (salidas), pero TinyDB solo tiene los
  roles `admin` · `manager` · `user`: pendiente de decidir si se restringe.
- **Sin interfaz:** no hay página del inventario en el backoffice.
