# Gestor de incidencias centralizado — TrackFlow

Registro único de las incidencias operativas y de clientes de TrackFlow (paquetes extraviados, fallos de carrier,
discrepancias de inventario, devoluciones, quejas), que hasta ahora llegaban por email o WhatsApp. Cada incidencia
queda registrada, categorizada, asociada a una sede y con su estado al día. Fuente de verdad de campos, valores,
mapeos y totales esperados: [`CONTEXT-gestor-incidencias.es.md`](../CONTEXT-gestor-incidencias.es.md).

Es una práctica del curso sin número de hito (como el directorio de proveedores y el analizador de incidencias), por lo
que no figura en [`hitos.md`](./hitos.md). Amplía lo ya construido: la misma API, el mismo backoffice y la validación
del [analizador de incidencias](./analizador-incidencias.md), cuyo CSV histórico se carga como datos iniciales.

> **No confundir con el analizador.** El *analizador* (`/incidencias` en el backoffice) lee un CSV y calcula métricas,
> sin guardar nada. El *gestor* (`/gestor-incidencias`) guarda incidencias y gestiona su ciclo de vida. Comparten el
> prefijo `/api/incidents` de la API y el paquete `packages/analisis-incidencias`.

## Arquitectura

```text
CONTEXT-gestor-incidencias.es.md        ← campos, valores, transiciones, mapeos CSV → modelo y totales esperados
packages/analisis-incidencias/
└── src/analisis_incidencias/gestor.py  ← valores, validación, transiciones y transformación del CSV (solo stdlib)
scripts/
├── seed_incidents.py                   ← carga el CSV histórico (idempotente)
└── incidents-trackflow.csv             ← CSV del analizador: 100 filas, 95 válidas
services/api/
├── app/incident_models.py              ← modelos Pydantic (enums y reglas salen de gestor.py)
├── app/services/incidents.py           ← alta, listado, detalle, cambio de estado y resumen sobre TinyDB
├── app/routes/incident_manager.py      ← los 5 endpoints; errores 400 y 500 propios del router
├── app/database.py                     ← tabla `incidents` en db/incidents.json
└── tests/test_incident_*.py, test_seed_incidents.py
uis/backoffice/
├── app/(panel)/gestor-incidencias/     ← page.tsx (resumen + listado) y nueva/page.tsx (formulario)
├── components/gestor-incidencias/      ← IncidentForm, IncidentDashboard, IncidentSummary, IncidentList, IncidentRow
├── lib/incidents.ts                    ← llamadas a la API, validación en cliente y mensajes de error
├── lib/data/incidents.ts               ← valores y etiquetas (las de sede, literales del CONTEXT)
└── types/incidents.ts
```

```text
CSV histórico ─► validar_registro (analizador) ─► gestor.transformar_fila ─┐
                                                                           ├─► IncidentRecord ─► TinyDB (incidents.json)
Formulario del backoffice ─► POST /api/incidents ─► gestor.validar_campo ──┘
```

**Una sola validación.** Los valores permitidos y las reglas viven en `gestor.py`. La API construye sus enums a partir
de ese módulo y el seed pasa cada fila por el mismo modelo que la API antes de guardarla: nada llega a la base sin
validar, venga del formulario, del seed o de un cambio de estado. El backoffice repite los valores en TypeScript
([`lib/data/incidents.ts`](../uis/backoffice/lib/data/incidents.ts)), como ya hace con proveedores.

**No va en `packages/shared`.** Ese paquete es TypeScript; la validación compartida entre el seed y la API es Python y
ya estaba en `packages/analisis-incidencias`.

## Modelo `Incident`

| Campo | Lo pone | Valores |
| --- | --- | --- |
| `id` | servidor | entero que asigna TinyDB |
| `title` | cliente, obligatorio | texto de 1 a 120 caracteres |
| `description` | cliente, **obligatorio** | texto de 1 a 2.000 caracteres (el máximo es un límite técnico, no del CONTEXT) |
| `category` | cliente, obligatorio | `lost_parcel` · `delivery_failure` · `inventory_discrepancy` · `carrier_issue` · `returns_issue` · `warehouse_incident` · `system_failure` · `client_complaint` · `other` |
| `status` | servidor | `open` (al crear) · `in_progress` · `resolved` · `discarded` |
| `origin` | cliente, obligatorio | `customer` · `branch` · `internal` |
| `branch` | cliente, **obligatorio siempre** | `central` · `la_warehouse` · `la_office` · `zaragoza_warehouse` · `zaragoza_office` |
| `created_at` | servidor | fecha y hora UTC |
| `updated_at` | servidor | fecha y hora UTC; se renueva en cada cambio de estado y nunca es anterior a `created_at` |

Etiquetas de las sedes (literales del CONTEXT): Central · Los Ángeles — Almacén · Los Ángeles — Oficina · Zaragoza —
Almacén · Zaragoza — Oficina. Cuando el origen es `internal` o `customer` y no corresponde a una instalación concreta,
se usa `central`.

**Transiciones:** `open → in_progress`, `open → discarded`, `in_progress → resolved`, `in_progress → discarded`.
`resolved` y `discarded` son finales.

**Integridad.** TinyDB es un fichero JSON y no impone restricciones: la integridad la garantiza el modelo Pydantic
`IncidentRecord`, por el que pasa toda escritura. No hay migraciones; la tabla se crea al primer uso.

## Requisitos e instalación

| Herramienta | Versión probada |
| --- | --- |
| Python | 3.14.6 (la API pide ≥ 3.12) |
| uv | 0.12.19 |
| Node.js / npm | 24.19 / 11.17 |

Desde la raíz del repo, en Windows PowerShell (un comando por línea):

```powershell
cd services\api
uv sync
Copy-Item .env.example .env
```

Edita `services\api\.env` y pon una `SECRET_KEY` propia (el fichero explica cómo generarla). Después:

```powershell
cd ..\..\uis\backoffice
npm install
Copy-Item .env.example .env.local
```

## Configuración

| Variable | Dónde | Por defecto | Para qué |
| --- | --- | --- | --- |
| `INCIDENTS_DB_PATH` | API | `services/api/db/incidents.json` | Fichero TinyDB del gestor (ignorado en git) |
| `SECRET_KEY` | API | — (obligatoria) | Firma de los JWT; sin ella la API no arranca |
| `CORS_ALLOWED_ORIGINS` | API | `http://localhost:3002,…` | Orígenes del backoffice |
| `NEXT_PUBLIC_API_BASE_URL` | backoffice | `http://localhost:8000` | URL de la API; se incrusta al compilar |

El resto de variables de la API (autenticación y email) están en [`services/api/README.md`](../services/api/README.md).

## Seed del CSV histórico

Carga [`scripts/incidents-trackflow.csv`](../scripts/incidents-trackflow.csv) en la base del gestor. Desde la **raíz
del repo**, con la **API parada** (el candado de TinyDB no protege entre procesos):

```powershell
uv run --project services/api python scripts/seed_incidents.py
```

Acepta la ruta de otro CSV como argumento. Con el Python del sistema (sin TinyDB) termina con código 2 e indica este
comando. Salida real de la primera ejecución:

```text
Registros descartados:
  - línea 4 · TRF-000003: Número de seguimiento inválido
  - línea 26 · TRF-000025: Transportista inválido para el país
  - línea 43 · TRF-000042: Categoría ausente o inválida
  - línea 69 · TRF-000068: Email ausente o inválido
  - línea 98 · TRF-000097: Cerrada sin puntuación

Seed completado.
  Filas leídas:  100
  Válidas:        95
  Insertadas:     95
  Duplicadas:      0
  Inválidas:       5
  Errores:         0

Incidencias en la base: 95 (95 del CSV)
  Por estado (CSV):    open 29 · resolved 52 · discarded 14
  Por categoría (CSV): lost_parcel 14 · delivery_failure 19 · carrier_issue 45 · returns_issue 17
```

La segunda ejecución da `Insertadas: 0` y `Duplicadas: 95`, y el fichero de la base no cambia ni un byte.

Qué hace con cada fila:

1. La valida con `validar_registro`, la misma lógica del analizador. Las que fallan se descartan y se listan.
2. La transforma según el CONTEXT:

   | CSV | Modelo |
   | --- | --- |
   | `description` | `title` (primeros 120 caracteres, recortados) y `description` (literal) |
   | `date` (`YYYY-MM-DD`) | `created_at` = `updated_at` = medianoche UTC |
   | `status`: `OPEN` · `CLOSED` · `DISCARDED` | `open` · `resolved` · `discarded` |
   | `category`: `LOST_PARCEL` · `DELAYED_DELIVERY` · `WRONG_ADDRESS` · `RETURN_REQUEST` · `DAMAGE` | `lost_parcel` · `carrier_issue` · `delivery_failure` · `returns_issue` · `carrier_issue` |
   | `country`: `US` · `ES` | `la_office` · `zaragoza_office` |
   | — | `origin` = `customer` |

3. La pasa por el modelo `IncidentRecord`, el mismo que usa la API.
4. La inserta si su `incident_id` no está ya en la base.

**Idempotencia.** El `incident_id` del CSV se guarda como referencia interna (`source_id`) y la API nunca lo devuelve.
Sin guardarlo, una segunda ejecución no podría reconocer lo ya cargado: la alternativa `title + created_at` solo da 88
claves distintas para las 95 filas válidas. El seed no modifica las incidencias existentes (conserva los estados
cambiados después) ni cuenta como duplicadas las registradas a mano. Los correos de clientes del CSV no se imprimen ni
se guardan.

Para empezar de cero, con la API parada, borra `services\api\db\incidents.json` y vuelve a ejecutar el seed.

## Ejecución

En dos terminales, desde la raíz del repo:

```powershell
cd services\api
uv run --env-file .env uvicorn app.main:app --port 8000
```

```powershell
cd uis\backoffice
npm run dev
```

Abre <http://localhost:3002>, inicia sesión (o regístrate en `/register`) y entra en **Incidencias** o **Registrar
incidencia** desde el menú. La documentación interactiva de la API está en <http://localhost:8000/docs>.

## Endpoints

Todos exigen `Authorization: Bearer <token>` (401 sin él). Implementación:
[`app/routes/incident_manager.py`](../services/api/app/routes/incident_manager.py).

| Método y ruta | Éxito | Errores |
| --- | --- | --- |
| `POST /api/incidents` | 201 + incidencia creada, en estado `open` | 400 datos no válidos |
| `GET /api/incidents` | 200 + lista, de la más reciente a la más antigua; `[]` si no hay datos | 400 filtro con un valor que no existe |
| `GET /api/incidents/summary` | 200 + totales por estado, categoría, origen y sede | — |
| `GET /api/incidents/{id}` | 200 + incidencia | 404 · 400 si el id no es un número |
| `PATCH /api/incidents/{id}/status` | 200 + incidencia con el nuevo estado y `updated_at` renovado | 400 transición no permitida o estado desconocido · 404 |

- **Filtros** de `GET /api/incidents`, opcionales y combinables: `status`, `origin`, `branch`, `category`.
- `POST` ignora `id`, `status`, `created_at` y `updated_at` si el cliente los envía.
- `/summary` devuelve siempre todas las claves, a 0 si no hay incidencias:

```json
{
  "total": 95,
  "by_status": { "open": 29, "in_progress": 0, "resolved": 52, "discarded": 14 },
  "by_category": { "lost_parcel": 14, "delivery_failure": 19, "inventory_discrepancy": 0, "carrier_issue": 45, "returns_issue": 17, "warehouse_incident": 0, "system_failure": 0, "client_complaint": 0, "other": 0 },
  "by_origin": { "customer": 95, "branch": 0, "internal": 0 },
  "by_branch": { "central": 0, "la_warehouse": 0, "la_office": 50, "zaragoza_warehouse": 0, "zaragoza_office": 45 }
}
```

Esos son los totales reales tras el seed y coinciden con los valores esperados del CONTEXT.

## Manejo de errores

| Situación | Respuesta |
| --- | --- |
| Datos no válidos (campo ausente, vacío, de otro tipo, demasiado largo o con un valor no permitido) | **400** `{"detail": [{"field": "description", "loc": ["body", "description"], "msg": "La descripción es obligatoria."}]}` |
| Transición no permitida | **400** en el campo `status`: «No se puede pasar de open a resolved. Desde open solo se admite: in_progress, discarded.» |
| Cambio desde un estado final | **400**: «La incidencia está en un estado final (resolved) y ya no admite cambios de estado.» |
| Incidencia inexistente | **404** `{"detail": "Incidencia 9999 no encontrada"}` |
| Sin token o token no válido | **401** |
| Cualquier error inesperado | **500** `{"detail": "Error interno del servidor."}`; la traza queda solo en el log del servidor |

- Los mensajes van en español, identifican el campo y no devuelven el valor recibido.
- El 400 se aplica **solo a las rutas del gestor**, con una clase de ruta propia. Proveedores y autenticación siguen
  devolviendo el 422 de FastAPI.
- El 500 del gestor se captura dentro de su router, de modo que conserva las cabeceras CORS y el backoffice puede
  leerlo. Además, `app/main.py` tiene un manejador global para cualquier otra ruta; Starlette lo ejecuta fuera del
  middleware de CORS, así que desde otro origen el navegador lo ve como un fallo de conexión.

## Uso en el backoffice

| Ruta | Qué hace |
| --- | --- |
| `/gestor-incidencias` | Panel de **resumen** (tarjetas por estado y barras por categoría, sede y origen) y **listado** con filtros por estado, origen, sede y categoría. Cada fila ofrece solo las transiciones permitidas. |
| `/gestor-incidencias/nueva` | **Formulario** de registro: título, descripción, categoría, origen y sede, todos obligatorios. |

- **Formulario.** Controles de 48 px de alto para terminales táctiles de almacén y solo dos campos de texto libre.
  Valida en cliente con los mismos mensajes que la API y lleva el foco al primer campo con error. Cuando el origen es
  «Sede», el campo de sede se destaca. Durante el envío el botón se deshabilita y un segundo envío se ignora. Tras
  registrar, muestra la confirmación con el número de la incidencia y limpia el formulario.
- **Listado.** Estados de carga, vacío (distinto si es por los filtros) y error con «Reintentar». El cambio de estado
  es optimista: la fila cambia al instante y, si la API falla o lo rechaza, vuelve al estado anterior y muestra el
  motivo en la propia fila.
- **Resumen.** Tiene su propia petición y sus propios estados de carga y error: si falla, el listado sigue
  funcionando. Se actualiza tras un cambio de estado correcto o al pulsar «Actualizar», y no depende de los filtros.
- **Errores.** La interfaz nunca muestra trazas, JSON ni mensajes internos: los errores del servidor se sustituyen por
  un texto fijo.

Las etiquetas de categoría, origen y estado son la traducción al español de cada código; las de sede son las del
CONTEXT. El backoffice no tiene soporte bilingüe, así que la nota del CONTEXT sobre el idioma no aplica.

## Tests

```powershell
python -m pytest scripts/tests packages/analisis-incidencias/tests
```

```powershell
cd services\api
uv run pytest -q
```

| Dónde | Tests | Qué cubren |
| --- | --- | --- |
| [`packages/analisis-incidencias/tests/test_gestor.py`](../packages/analisis-incidencias/tests/test_gestor.py) | 122 | Valores, etiquetas, transiciones y mapeos contrastados con el CONTEXT (leyéndolo); validación campo a campo; transformación del CSV; el CSV histórico produce los totales esperados |
| [`services/api/tests/test_incident_models.py`](../services/api/tests/test_incident_models.py) | 73 | Modelos, integridad, tabla TinyDB, datos inválidos que no llegan a la base |
| [`services/api/tests/test_seed_incidents.py`](../services/api/tests/test_seed_incidents.py) | 22 | Totales esperados, idempotencia, inválidas reportadas, sin correos, casos límite y errores de fichero |
| [`services/api/tests/test_incident_manager.py`](../services/api/tests/test_incident_manager.py) | 183 | Los 5 endpoints: éxito, 400 por campo, filtros, 404, las 16 combinaciones de transición, resumen con y sin datos, 401, 500 sin traza, convivencia con el analizador y con proveedores |

Totales del repo tras esta práctica: 192 tests en el paquete y los scripts, y 751 en la API. Los tests del seed viven en
la API porque necesitan TinyDB. Ningún test toca `db/incidents.json`: cada uno usa una base temporal.

Las pruebas en navegador (Edge + `playwright-core`) se hacen fuera del repo, como en el resto del backoffice, contra la
API real con bases temporales: formulario 69/69, listado 64/64, resumen 33/33, flujo de extremo a extremo 44/44 y
regresión de inicio, proveedores, analizador y sesión 22/22.

## Capturas

Tomadas por el desarrollador en local, con el seed cargado (carpeta
[`uis/backoffice/screenshots/`](../uis/backoffice/screenshots/)):

| Evidencia | Captura |
| --- | --- |
| Formulario con error de validación | [`screenshot gestor formulario validacion.png`](../uis/backoffice/screenshots/screenshot%20gestor%20formulario%20validacion.png) |
| Listado con datos | [`screenshot gestor listado.png`](../uis/backoffice/screenshots/screenshot%20gestor%20listado.png) |
| Resumen con métricas | [`screenshot gestor resumen.png`](../uis/backoffice/screenshots/screenshot%20gestor%20resumen.png) |

## Limitaciones

- La integridad es de aplicación: quien edite `incidents.json` a mano se salta la validación (la API responde 500
  genérico si encuentra un documento corrupto).
- El candado de TinyDB no protege entre procesos: el seed se ejecuta con la API parada, y la API con un solo worker.
- Sin paginación: `GET /api/incidents` devuelve todas las incidencias.
- Sin edición ni borrado de incidencias (solo alta y cambio de estado), y sin historial de cambios de estado: solo se
  guarda el último `updated_at`.
- Cualquier usuario autenticado puede registrar incidencias y cambiar su estado; no hay permisos por rol ni por sede.
- No se guarda quién registra ni quién cambia cada incidencia.
- Las alertas del CONTEXT (incidencias críticas con más de 24 horas abiertas) no forman parte de esta práctica. El
  modelo las facilita: `category`, `status`, `branch` y `created_at` se pueden filtrar.
- Tras cambiar un estado, la fila sigue visible aunque ya no cumpla el filtro activo, hasta pulsar «Actualizar».
- Las incidencias del seed tienen como hora la medianoche UTC del CONTEXT, que el backoffice muestra en la hora local
  del navegador.
- La API no está desplegada: el gestor funciona en local. Ver [`despliegue-api.md`](./despliegue-api.md).
