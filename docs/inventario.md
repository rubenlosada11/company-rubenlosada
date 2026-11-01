# Gestión de inventario backend — Hito 5 (TrackFlow)

API de inventario unificada para los SKUs de los almacenes de **Los Ángeles (`LA`)** y **Zaragoza (`ZGZ`)** (ticket
Linear TRK-0341 de Andrés Kim, CTO). Registra cada unidad que entra (recepción de mercancía de una marca cliente) y
que sale (despacho a un cliente o pérdida confirmada). El stock **nunca se guarda**: se calcula siempre como entradas
menos salidas, y por almacén. Fuente de verdad de entidades, campos, rutas, reglas y datos semilla:
[`CONTEXT-gestor-inventario.es.md`](../CONTEXT-gestor-inventario.es.md).

Es el **Hito 5** del proyecto (ver [`hitos.md`](./hitos.md)). La API vive en la existente
([`services/api`](../services/api/README.md)), con su autenticación JWT de TinyDB, y el backoffice tiene su interfaz
de operaciones en `/inventory/…` (ver [Interfaz en el backoffice](#interfaz-en-el-backoffice)).

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
- **Supabase / PostgreSQL:** se define `DATABASE_URL` con la cadena *Session pooler* de Supabase. La API trae el
  driver `psycopg[binary]` (conexión con 10 s de tiempo máximo) y está probada contra PostgreSQL 16; la contraseña
  solo va en tu `.env`. Pasos en [Conectar Supabase](#conectar-supabase).
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

118 tests (HTTP de los 6 endpoints, reglas 1–6, salidas simultáneas, base no disponible, seed y motor SQL), cada uno con su propia base
SQLite temporal (el `conftest.py` fija `DATABASE_URL`: nunca tocan `db/inventory.db` ni una base real). Cobertura de
líneas y ramas: 100 % en modelos, schemas, router y servicio; 95 % en el seed. Además se hicieron 8 pruebas de mutación
manuales (quitar el candado, `>` por `>=`, sumar los almacenes, quitar cada regla de `tracking_number`, tomar
`user_uuid` del cuerpo, quitar la autenticación): todas hacen fallar algún test.

**Contra PostgreSQL real (2026-11-01):** con un PostgreSQL 16 local (`pgserver`, fuera del repo) pasaron los 107 tests
del inventario que usan la base (incluidas las 10 salidas simultáneas con `SELECT … FOR UPDATE`; los 4 restantes
cambian `DATABASE_URL` a propósito), el seed (dos veces, sin duplicar) y los 6 endpoints con `curl`, antes y después de
activar RLS. Esquema creado: `timestamptz` en `created_at`, claves foráneas e índice único en `skus.sku`.

## Interfaz en el backoffice

Cuatro vistas en [`uis/backoffice`](../uis/backoffice/README.md#qué-muestran-las-rutas-inventory), dentro del panel
protegido (sin sesión → `/login?next=<ruta>`; un 401 de la API cierra la sesión):

| Ruta del backoffice | Qué hace | Endpoints |
| --- | --- | --- |
| `/inventory/products` | SKUs con `current_stock`, desglose del otro almacén si tiene unidades, indicador de nivel y accesos a registrar entrada o salida del producto (`?sku_id=`) | `GET /inventory/products` |
| `/inventory/orders/inbound` | Recepción: producto por nombre, cantidad y referencia; stock actual del producto elegido | `GET /inventory/products`, `GET /inventory/products/{id}`, `POST /inventory/orders/inbound` |
| `/inventory/orders/outbound` | Despacho o pérdida con stock reactivo, aviso y bloqueo si la cantidad supera el stock, y el 400 de la regla 2 en español junto a la cantidad | `GET /inventory/products`, `GET /inventory/products/{id}`, `POST /inventory/orders/outbound` |
| `/inventory/orders` | Historial de solo lectura con producto, cantidad, tipo, fecha y `user_uuid`; filtros por almacén y producto | `GET /inventory/orders` |

- **Integración:** un único módulo, [`uis/backoffice/lib/inventory.ts`](../uis/backoffice/lib/inventory.ts), sobre el
  cliente común `lib/http.ts` (Bearer de la sesión, 401, tiempo máximo y errores). URL:
  `NEXT_PUBLIC_INVENTORY_API_URL` o, si no está, `NEXT_PUBLIC_API_BASE_URL` (la misma API, que valida el mismo token).
- **Umbrales de stock** (de presentación, no de negocio): agotado ≤ 0, crítico 1–10, bajo 11–30, saludable > 30.
- **Regla 2 en la interfaz:** el aviso de stock insuficiente es una ayuda; el backend sigue decidiendo. Si el stock ha
  cambiado desde que se consultó, la API responde 400 y el formulario muestra
  «Stock insuficiente para el SKU … : hay N unidades disponibles y has pedido M unidades.», conserva los datos y vuelve
  a pedir el stock.
- **Regla 6:** la interfaz muestra `current_stock` (almacén del SKU) y, aparte, el stock del otro almacén; nunca un total.
  Los movimientos se registran en el almacén del SKU (el formulario no envía `warehouse`).

**Pruebas de la interfaz (2026-11-01):** Jest `lib/inventory.test.ts` (57 tests, 99 % de líneas de `lib/inventory.ts`;
3 mutaciones detectadas) y pruebas en navegador fuera del repo (Edge + `playwright-core` + `axe-core`) contra una API
de prueba con bases temporales y `next start`: productos 18/18, entrada 29/29, salida 35/35 (incluido un 400 real del
backend y el cambio rápido de producto), historial 21/21, integración 41/41 (navegación, stock coherente al volver al
listado, axe WCAG A/AA sin incidencias en las cuatro vistas, 390 y 768 px) y sesión 12/13 (ver limitaciones).

**Capturas de la interfaz:** tomadas por el desarrollador en local (API con SQLite y datos semilla, usuario ficticio),
en [`uis/backoffice/screenshots/gestión de inventario/`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/). Las tres de «Salida 400»
reproducen el caso del stock que cambia entre que se consulta y se envía: el backend tiene la última palabra.

| Evidencia | Qué muestra | Captura |
| --- | --- | --- |
| Listado de productos | `/inventory/products`: 6 SKUs con `current_stock` y su nivel (saludable, bajo, crítico) y las tarjetas de recuento | [`Listado de productos.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Listado%20de%20productos.jpeg) |
| Entrada: formulario | Producto elegido por nombre · SKU · almacén y su stock actual (9, crítico) antes de registrar 25 unidades | [`Registro de entrada producto.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20de%20entrada%20producto.jpeg) |
| Entrada: confirmación | «Entrada n.º 8 registrada» con el stock nuevo (34) y el formulario limpio | [`Registro de entrada producto confirmación y stock actual.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20de%20entrada%20producto%20confirmaci%C3%B3n%20y%20stock%20actual.jpeg) |
| Salida: aviso de stock | Despacho de 56 con 52 disponibles: aviso junto a la cantidad y botón desactivado | [`Registro de salida con aviso de stock.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20de%20salida%20con%20aviso%20de%20stock.jpeg) |
| Salida 400 (1/3): pestaña A | Pérdida de 20 con 28 disponibles, válida, sin enviar | [`Registro salida pestaña A sin enviar.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20salida%20pesta%C3%B1a%20A%20sin%20enviar.jpeg) |
| Salida 400 (2/3): pestaña B | Otra salida de 15 del mismo producto en otra pestaña: quedan 13 | [`Registro salida pestaña B y actualización de stock.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20salida%20pesta%C3%B1a%20B%20y%20actualizaci%C3%B3n%20de%20stock.jpeg) |
| Salida 400 (3/3): pestaña A enviada | La API rechaza la salida (400) y el mensaje sale en español junto a la cantidad; el stock se vuelve a pedir (13) | [`Registro salida pestaña A enviada y aviso stock.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Registro%20salida%20pesta%C3%B1a%20A%20enviada%20y%20aviso%20stock.jpeg) |
| Historial completo | `/inventory/orders`: 15 movimientos con tipo, producto, cantidad con signo, fecha, detalle y `user_uuid` («Tú») | [`Historial de movimientos completo.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Historial%20de%20movimientos%20completo.jpeg) |
| Historial filtrado | Filtro por producto: los 4 movimientos de un SKU | [`Historial de movimientos completo con filtro producto.jpeg`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Historial%20de%20movimientos%20completo%20con%20filtro%20producto.jpeg) |
| Ruta protegida | Sin sesión, `/inventory/products` lleva a `/login?next=%2Finventory%2Fproducts` | [`Ruta protegida.png`](../uis/backoffice/screenshots/gesti%C3%B3n%20de%20inventario/Ruta%20protegida.png) |

## Conectar Supabase

La API ya trae el driver de PostgreSQL (`psycopg[binary]`) y se probó contra un **PostgreSQL 16 local** (los 107 tests
del inventario que usan la base, el seed y los 6 endpoints, también con RLS activado). **Conectado el 2026-11-01** al
proyecto de Supabase del equipo (PostgreSQL 17, *Session pooler* en `eu-west-1`, SSL): seed cargado (6 SKUs, 7
entradas, 4 salidas), RLS activado en las tres tablas y stock por almacén correcto. La contraseña solo va en el `.env`
de cada desarrollador (nunca en git ni en un chat); quien quiera usar la misma base repite los pasos 2–4 y 6.

Comandos en **PowerShell**, uno por línea, desde `services\api`.

### 1. Crear (o elegir) el proyecto

1. Entra en <https://supabase.com/dashboard> con la cuenta de TrackFlow.
2. **New project** → organización de la cuenta, nombre `trackflow` (o el que prefieras), **Database Password** con
   *Generate a password* y **guárdala en tu gestor de contraseñas** (Supabase no la vuelve a mostrar). Región: la más
   cercana a donde corra la API (p. ej. *West EU (Ireland)* si la arrancas desde España). Plan Free.
3. Espera a que el proyecto termine de crearse (un par de minutos).

Si ya tienes un proyecto, sirve el mismo: las tablas `skus`, `stock_entries` y `stock_exits` se crean en el esquema
`public` y no tocan nada más (si ya existieran tablas con esos nombres, avisa antes de seguir).

### 2. Copiar la cadena de conexión *Session pooler*

1. En el proyecto, botón **Connect** (arriba) → cadena de conexión → método **Session pooler**.
2. Copia la URI. Tiene esta forma (el host exacto, `aws-<n>-<región>.pooler.supabase.com`, cópialo tal cual):
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@<host-del-pooler>:5432/postgres`

Por qué *Session pooler*: la conexión directa (`db.<project-ref>.supabase.co`) solo funciona por IPv6 salvo que se pague
el complemento IPv4, y el *Transaction pooler* (puerto 6543) no admite *prepared statements*, que psycopg usa.

### 3. Ponerla en `services/api/.env`

Edita tu `.env` (ignorado en git; si no existe, `Copy-Item .env.example .env`) y añade la línea con estos cambios sobre
la URI copiada:

- prefijo `postgresql+psycopg://` en vez de `postgresql://`;
- tu contraseña en lugar de `[YOUR-PASSWORD]` (sin los corchetes);
- `?sslmode=require` al final (cifra la conexión);
- todo **entre comillas dobles**.

```dotenv
DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:<contraseña>@<host-del-pooler>:5432/postgres?sslmode=require"
```

Si la contraseña tiene `@ : / ? # % &` o espacios, codifícala antes de pegarla (la generada por Supabase no suele
tenerlos):

```powershell
[uri]::EscapeDataString('tu-contraseña')
```

### 4. Instalar dependencias, crear las tablas y cargar los datos

```powershell
cd services\api
uv sync
uv run --env-file .env seed-inventory
```

La primera ejecución crea las tablas y carga 6 SKUs, 7 entradas y 4 salidas, firmadas por el primer administrador de
`db/auth.json` (o el email que pases: `uv run --env-file .env seed-inventory <email>`). Si la repites, no duplica nada.
La URL que imprime oculta la contraseña. Si falla con `OperationalError`, revisa host, usuario
(`postgres.<project-ref>`, con el punto), contraseña y que el proyecto no esté pausado.

### 5. Activar RLS en las tres tablas

En Supabase → **SQL Editor** → *New query*, ejecuta:

```sql
alter table public.skus enable row level security;
alter table public.stock_entries enable row level security;
alter table public.stock_exits enable row level security;
```

Por qué: las tablas creadas por SQL (como hace SQLModel) no llevan RLS. Desde el 30-10-2026 Supabase ya no las expone en
su API pública (Data API) sin un `GRANT`, pero activar RLS sin políticas cierra esa puerta igualmente si algún día se
expone el esquema. A la API de TrackFlow no le afecta: se conecta como `postgres`, dueño de las tablas (probado en
local: lecturas y escrituras siguen funcionando). Comprueba después **Advisors → Security Advisor**: no debería quedar
ningún aviso de estas tablas.

### 6. Arrancar la API y comprobarlo

```powershell
uv run --env-file .env uvicorn app.main:app --reload --port 8000
```

1. En Supabase → **Table Editor**: `skus` (6 filas), `stock_entries` (7) y `stock_exits` (4).
2. En <http://localhost:8000/docs>: **Authorize** con tu usuario y `GET /inventory/products` → `CLT-SNK-W-42` con
   `current_stock` 53, `CSM-SRM-030` con 117, etc. (ver [Datos semilla](#datos-semilla)).
3. Una salida de 29 unidades de `CLT-SNK-W-42-Z` (`sku_id` 2, `ZGZ`) → 400 «Insufficient stock … Available: 28,
   requested: 29.»

### Volver a SQLite y otras notas

- Para volver a la base local, comenta la línea `DATABASE_URL` del `.env` y reinicia la API. Los datos de Supabase y
  de `db/inventory.db` son independientes.
- **Los tests nunca usan Supabase:** `tests/conftest.py` fija una base SQLite temporal en cada test.
- Si se filtra la contraseña: Supabase → **Project Settings → Database → Reset database password** y actualiza el
  `.env`.
- El plan Free **pausa el proyecto** tras unos días sin uso; se reactiva desde el panel (mientras tanto, `/inventory`
  responde 500 y el resto de la API sigue funcionando).
- Solo cambia la base del inventario: usuarios, proveedores e incidencias siguen en TinyDB (`db/*.json`).

## Limitaciones conocidas

- **Un solo worker.** El candado de la regla 2 protege los hilos de un proceso. En PostgreSQL, `SELECT … FOR UPDATE`
  bloquea además el SKU entre procesos; en SQLite con varios procesos no hay esa garantía.
- **Sin migraciones** (ver «Otras decisiones») ni paginación en los listados.
- **Permisos:** cualquier usuario autenticado puede registrar SKUs y movimientos, como en proveedores e incidencias. El
  briefing distingue operarios de almacén (entradas) y coordinadores logísticos (salidas), pero TinyDB solo tiene los
  roles `admin` · `manager` · `user`: pendiente de decidir si se restringe.
- **Interfaz:** sin alta de SKUs (la API la tiene, el hito no la pide), sin elegir otro almacén en los movimientos
  y con el `user_uuid` en el historial en lugar del nombre. Si se entra sin sesión a un formulario con `?sku_id=`, tras
  el login se pierde el producto preseleccionado (el `next` guarda la ruta, no la consulta).
- **Aviso «sesión caducada» intermitente (anterior al hito):** con un token ya caducado guardado, el login a veces
  aparece sin el aviso «Tu sesión ha caducado» (`motivo=caducada`). La redirección al login sí ocurre siempre. Se
  reproduce igual en `/proveedores`, así que está en la autenticación común (`AuthProvider`/`AuthGate`), fuera de este
  hito.
