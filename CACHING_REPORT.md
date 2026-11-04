# Informe de caching y optimización de rendimiento

Rama `feature/caching-optimisation` (desde `main` @ `79cf971`), noviembre de 2026. Mediciones, scripts y datos en
[`audit/caching/`](audit/caching/README.md). Todas las cifras de este informe están **medidas** salvo las que se
marcan como *estimación*. Cuando un dato no se ha podido medir, aparece como N/A.

## 1. Resumen ejecutivo

**Problema inicial.** Con un volumen de datos realista, varias lecturas de la API (`services/api`) recalculan en
cada petición lo mismo que en la anterior. `GET /inventory/products` agrega 33.000 movimientos de stock para devolver
1.000 SKUs (42 ms). `GET /api/incidents/summary` lee y parsea un JSON de 2,2 MB para devolver 468 bytes de totales
(20 ms). Con 8 peticiones simultáneas, el GIL y el candado de TinyDB las encolan: p95 de 1,0 s y 214 ms. En el
backoffice, cada pulsación en los formularios de inventario volvía a construir las `<option>` de todo el catálogo, y
dos pantallas descargaban de inicio código que solo se usa tras una acción.

**Objetivos.** Reducir esas latencias sin servir datos de un usuario a otro, sin cambiar el contrato de la API y sin
introducir infraestructura nueva (Redis, otra base, dependencias).

**Implementado.**

| Área | Cambio |
| --- | --- |
| Backend | Middleware de tiempos (`app/timing.py`): método, ruta normalizada, estado, ms y consultas SQL de cada petición |
| Backend | Caché en memoria con TTL e invalidación (`app/cache.py`) en `GET /inventory/products` (30 s) y `GET /api/incidents/summary` (60 s) |
| Frontend | Carga diferida del formulario de alta de proveedores y de los resultados del analizador de incidencias |
| Frontend | `useMemo` de las opciones del selector de producto de los formularios de entrada y salida de stock |

**Resultados principales** (medianas; detalle en §6):

| Medida | Antes | Después | Variación |
| --- | ---: | ---: | ---: |
| `GET /api/incidents/summary` | 20,24 ms | 1,62 ms | −92,0 % |
| `GET /inventory/products` | 42,15 ms | 7,57 ms | −82,0 % |
| `GET /inventory/products?warehouse=LA` | 34,91 ms | 5,00 ms | −85,7 % |
| Rendimiento con 8 hilos, resumen / inventario | 47,7 / 8,6 pet./s | 551,2 / 120,3 pet./s | ×11,6 / ×14,0 |
| Tasa de aciertos con carga mixta (9 lecturas : 1 escritura) | — | 86,8 % / 79,7 % | — |
| Pulsación en «Cantidad» con 1.001 productos (CPU ×4) | 4,9 ms | 1,0 ms | −80 % |
| JS inicial de `/incidencias` · `/proveedores` (gzip) | 156.503 · 156.787 B | 154.105 · 156.041 B | −1,5 % · −0,5 % |

Lo que **no** mejoró y se descartó también está medido: cachear el directorio de proveedores no aportaba nada (§8), y
`next/dynamic` y `React.lazy` hacían más lento el panel diferido (§4).

## 2. Arquitectura analizada

| Pieza | Estado real |
| --- | --- |
| Frontend | `uis/backoffice` (panel interno) y `uis/website` (web pública, estática): Next.js 16.3.4 con App Router, React 19.2.8, Tailwind 4, TypeScript 5. Componentes cliente que piden datos a la API con `fetch` (`lib/http.ts`, `useApiRequest`). Sin librerías de estado ni de datos |
| Backend | `services/api`: FastAPI 0.141, Pydantic 2.13, uvicorn, Python 3.14 en el equipo (≥ 3.12). Un único worker (`docs/despliegue-api.md`, Docker) |
| Bases de datos | TinyDB (ficheros JSON) para proveedores, incidencias y usuarios. SQLite por defecto (o PostgreSQL/Supabase con `DATABASE_URL`) para el inventario |
| ORM | SQLModel 0.0.48 (SQLAlchemy 2.1) solo en el inventario; TinyDB sin ORM |
| Autenticación | JWT Bearer (`python-jose`), comprobado en cada petición por `get_current_user`, que relee el usuario en TinyDB. Los routers de proveedores, incidencias e inventario lo exigen con `dependencies=[Depends(get_current_user)]` |
| Caching previo | Ninguno: sin `lru_cache`, `Cache-Control`, Redis ni `revalidate`. Solo `useMemo` en `AuthProvider` y `Explorer`. Las respuestas de la API no llevan cabeceras de caché HTTP |
| Tests | pytest (1.221 en la API, 196 del paquete del analizador y los scripts) y Jest en el backoffice (148) |

## 3. Línea base de rendimiento

**Método.** El middleware de tiempos (`time.perf_counter()` en un `try/finally`) registra cada petición. El script
`audit/caching/bench_api.py` lanza 10 peticiones de calentamiento y 200 medidas por endpoint, secuenciales, con los
mismos parámetros y una conexión persistente. Después repite las mismas peticiones con 8 hilos. Mide la latencia en
el cliente y lee del log del servidor el tiempo de aplicación y el número de consultas SQL. Como «antes» se usa el
código de la rama con el middleware y **sin caché**: una copia del paquete `app/` con las rutas y servicios de `main`.

**Dataset.** Las bases locales (15 proveedores, 95 incidencias, 6 SKUs, 15 movimientos) son demasiado pequeñas para
medir algo útil. `audit/caching/seed_benchmark.py` genera un dataset ficticio y reproducible (semilla fija) que
respeta las claves foráneas y la regla de stock nunca negativo, siempre en un directorio nuevo (se niega a escribir
en `services/api/db`). La API medida se arranca sobre **copias** de ese dataset; nunca se toca Supabase.

| Base | Registros reales en local | Dataset de benchmark |
| --- | ---: | ---: |
| Proveedores | 15 | 500 |
| Incidencias | 95 | 5.000 (2,2 MB) |
| SKUs | 6 | 1.000 (500 por almacén) |
| Entradas / salidas de stock | 8 / 7 | 20.000 / 13.403 |

**Inventario de endpoints de lectura** (mediana en el servidor, primera medición completa sin caché):

| Endpoint | Operación | Coste | Consultas | Frecuencia (*estimación*) | Estabilidad | ¿Candidato? |
| --- | --- | ---: | ---: | --- | --- | --- |
| `GET /inventory/orders` | Historial completo (11,7 MB) | 1.249 ms | 2 | Media | Cambia con cada movimiento | No (§8) |
| `GET /api/incidents` | Lista completa (1,8 MB) | 81 ms | — | Alta | Cambia con cada estado | No (§8) |
| `GET /inventory/products` | SKUs + 2 agregaciones de stock | 43 ms | 3 | Alta (listado, selectores) | Cambia con cada movimiento, todos pasan por la API | **Sí** |
| `GET /inventory/products?warehouse=LA` | Ídem, un almacén | 35 ms | 3 | Alta | Ídem | **Sí** |
| `GET /api/incidents?status=…` | Lista filtrada | 22 ms | — | Media | Cambia con cada estado | No |
| `GET /api/incidents/summary` | Lee el fichero entero y cuenta | 20 ms | — | Alta (panel del gestor) | Cambia con altas y estados | **Sí** |
| `GET /api/incidents/{id}` | Una incidencia | 15 ms | — | Baja | — | No |
| `GET /suppliers` | 500 proveedores | 7,5 ms | — | Media | Muy estable | Probado y descartado (§8) |
| `GET /inventory/products/{id}` | Un SKU + su stock | 3,4 ms | 3 | Alta en formularios | Debe ser exacto | No (§8) |
| `GET /auth/me`, `GET /profiles/me` | Datos del usuario | 2–3 ms | — | Alta | Personales | No (§8) |
| `GET /health` | Constante | 0,9 ms | — | Docker | — | No |

No hay N+1: el inventario hace 2 o 3 consultas por petición, agregadas en SQL. Ningún endpoint llama a servicios
externos (el email de AUTH-03 solo se envía al pedir un enlace de recuperación).

**Limitaciones de las mediciones.** Un solo equipo Windows con otros procesos en marcha. Entre dos ejecuciones
completas, los endpoints **sin cambios** variaron hasta ×2 (p. ej. `/health` 0,9–1,9 ms). Por eso la comparación
principal (§6) usa **rondas alternas**: `interleave.py` mide antes y después cinco veces cada uno, intercalados, y
toma la mediana de las medianas, con endpoints sin caché como control. Es SQLite local: con PostgreSQL en Supabase,
cada consulta suma la latencia de red (no medida), así que un acierto ahorraría más. Las cifras son de un worker.

## 4. Decisiones en frontend

Solo se ha tocado `uis/backoffice`: `uis/website` es una web estática de componentes de servidor, sin componentes
pesados ni cálculos en el cliente.

### Carga diferida

| | Formulario de alta de proveedor | Resultados del analizador de incidencias |
| --- | --- | --- |
| Componente | `SupplierForm` (262 líneas: campos, validación, envío) | `ResultadosAnalisis` + `ListaBarras`, `TablaSatisfaccion`, `TablaCruce`, `RegistrosInvalidos` |
| Ubicación | `components/SupplierDirectory.tsx` (`/proveedores`) | `components/incidencias/AnalizadorIncidencias.tsx` (`/incidencias`) |
| Cuándo se usa | Solo al pulsar «Nuevo proveedor» | Solo después de analizar un CSV |
| Precarga | Al pasar el puntero o el foco por el botón | Al enviar el fichero, en paralelo con la petición a la API |
| Chunk bajo demanda | 2.078 B (gzip) | 3.097 B (gzip) |
| Chunk de la página | 7.477 → 6.691 B | 7.193 → 4.755 B |
| JS inicial de la ruta | 156.787 → 156.041 B (−746 B, −0,5 %) | 156.503 → 154.105 B (−2.398 B, −1,5 %) |

**Implementación: `import()` + `use()` + `Suspense`** (`lib/deferredModule.ts`). `import()` separa el componente
en su propio chunk, como `next/dynamic` y `React.lazy`. La promesa se guarda y se marca con `status`/`value` al
resolverse, así que si el módulo ya está precargado `use()` lo devuelve sin suspender y no aparece ningún «Cargando…».
Si la descarga falla, se olvida la promesa: el reintento la vuelve a pedir y el error lo recoge
`app/(panel)/error.tsx`. Los dos componentes nunca se renderizan en el servidor (dependen de un clic o de un fichero),
así que no hay SSR que conservar ni riesgo de hidratación: 0 errores de consola y de página en todas las mediciones.

**Por qué no `next/dynamic` ni `React.lazy`** (medido con el mismo script durante el desarrollo; esos builds
intermedios no se versionan):

| Técnica | JS inicial `/proveedores` · `/incidencias` | Clic → formulario visible | Envío → resultados visibles |
| --- | --- | ---: | ---: |
| Sin carga diferida (antes) | 156.787 · 156.503 B | 137 ms | 125 ms |
| `next/dynamic` | +431 · −1.250 B: añade un chunk de 3.035 B con su runtime (`BailoutToCSR`, `PreloadChunks`) | no medido | no medido |
| `React.lazy` + `Suspense` | −839 · −2.508 B | 457–686 ms | 871–891 ms |
| `import()` + `use()` + `Suspense` (final) | −746 · −2.398 B | 147 ms tras 150 ms sobre el botón; 459–696 ms con clic inmediato | 114–156 ms |

`React.lazy` (y `next/dynamic`, que lo usa por dentro) suspende al menos una vez aunque el chunk ya esté
descargado, y React 19 retrasa hasta 300 ms la sustitución de un fallback por su contenido
(`globalMostRecentFallbackTime + 300` en `react-dom`). Ahorrar 1–2 KB a cambio de 300–750 ms de espera visible no
compensaba.

**Beneficio.** Pequeño, y así se presenta: los dos componentes pesan 2–3 KB comprimidos frente a ~150 KB de framework
compartido por todas las rutas. El chunk de la página de incidencias baja un 34 %, y el análisis aparece igual de
rápido que antes porque el chunk llega antes que la respuesta de la API. **Coste residual:** con un clic inmediato,
sin pasar antes el puntero (pantallas táctiles), el formulario de proveedores tarda ~460–700 ms en lugar de 137 ms;
con ratón o teclado, la precarga llega a tiempo. Ver §10.

### `useMemo`

| | |
| --- | --- |
| Cálculo memoizado | Las `<option>` del selector de producto (`ProductSelect`, `components/inventory/formParts.tsx`): una por SKU, con su etiqueta «nombre · SKU · almacén» |
| Complejidad | O(n) elementos y cadenas por render, más la reconciliación de n `<option>` en el DOM. n = SKUs del inventario (1.001 opciones en el benchmark) |
| Cuándo se repetía | En **cada pulsación** de los formularios de entrada y salida (cantidad, referencia, número de seguimiento): el formulario se vuelve a renderizar y con él el selector |
| Dependencias | `[products.products]`, el array de la respuesta de la API. `useProducts` devuelve ahora una lista vacía estable (`NO_PRODUCTS`) en lugar de `data ?? []`, que era un array nuevo en cada render y anulaba la memoización |
| Por qué está justificado | Las opciones solo cambian cuando llega una lista nueva. Al devolver los mismos elementos, React se salta la reconciliación de todas las `<option>`. Sin estado nuevo ni mutaciones; resultado determinista |
| Beneficio medido | Tiempo hasta confirmar cada pulsación en «Cantidad» en `/inventory/orders/outbound`, Edge con CPU ×4, 7 rondas × 60 pulsaciones: mediana **4,9 → 1,0 ms** (rondas 4,3–5,8 → 0,7–1,4 ms) |

Con los 6 SKUs actuales la diferencia es inapreciable. Importa cuando el catálogo crece (cientos de SKUs por marca) y
en los terminales de almacén, que son menos potentes que un portátil.

## 5. Decisiones en backend

**Mecanismo: caché en memoria del proceso** (`app/cache.py`, solo biblioteca estándar + Pydantic). Descartes:

- **Redis.** El proyecto no lo tiene, despliega un único worker en un VPS de 1 GB y los datos cacheados caben en
  memoria. Añadiría un servicio, una dependencia y un punto de fallo sin necesidad hoy.
- **`functools.lru_cache`.** No tiene TTL, no permite invalidar por escritura sin vaciarlo entero y devuelve el mismo
  objeto mutable a todos los llamadores.

**Diseño común.**

- **Instantáneas inmutables.** Se guarda el JSON (`bytes`) generado con el `TypeAdapter` del `response_model`, y cada
  acierto devuelve objetos nuevos (`validate_json`): modificar una respuesta nunca cambia la caché. Las funciones del
  router siguen devolviendo sus modelos y FastAPI los serializa como siempre, así que el contrato no cambia. Se
  comprobó byte a byte contra la API sin caché, en fallo y en acierto, con el mismo `Content-Type`.
- **Claves deterministas.** Una tupla con el origen de los datos (ruta del fichero o URL de la base) y los parámetros
  ya validados por FastAPI (enums o `None`). Parámetros distintos dan claves distintas sin colisiones, y una base
  distinta (otra `DATABASE_URL`) nunca comparte entrada. Las claves no se registran en el log.
- **Invalidación por generación.** Cada escritura vacía la caché y sube un contador. Una lectura que empezó antes de
  la escritura no guarda su resultado, que podría ser viejo.
- **Errores.** Un error de la base se propaga como antes (500 genérico) y no se cachea. Si falla la propia caché, se
  registra y se responde con los datos recién leídos.
- **Límite de memoria.** Máximo 64 entradas por caché; si se llena, sale la que caduca antes. Hoy hay 3 claves
  posibles por base en el inventario (sin filtro, LA, ZGZ) y 1 en el resumen. Con el dataset de benchmark, las
  instantáneas ocupan unos 385 KB (192 + 96 + 97 KB) en el inventario y 0,5 KB en el resumen.

| | `GET /inventory/products` | `GET /api/incidents/summary` |
| --- | --- | --- |
| Datos | SKUs con `current_stock` y `stock_by_warehouse` | Totales por estado, categoría, origen y sede |
| Coste sin caché | 42 ms, 3 consultas (2 agregaciones sobre todos los movimientos) | 20 ms: lee y parsea el JSON entero para devolver 468 B |
| Frecuencia (*estimación*) | Alta: listado de productos, selectores de los formularios y del historial | Alta: panel del gestor de incidencias, recarga tras cada cambio de estado |
| Cambios de los datos | Cada entrada, salida o alta de SKU (pasan todas por la API) | Cada alta y cambio de estado (pasan todos por la API) |
| TTL | **30 s** | **60 s** |
| Clave | `(DATABASE_URL o SQLite local, warehouse)` | `(ruta de incidents.json,)` |
| Invalidan | `create_sku`, `register_entry`, `register_exit`, **después** del commit | `create_incident`, `update_status`, **después** de escribir |
| No invalidan | SKU duplicado (409), stock insuficiente (400), SKU inexistente (404), datos no válidos (422) | Transición no permitida (400), incidencia inexistente (404), datos no válidos (400) |
| Riesgos de consistencia | Escrituras de otros procesos (seed, otro worker, SQL directo en Supabase): visibles en ≤ 30 s | Escrituras de otros procesos (`scripts/seed_incidents.py`, que se ejecuta con la API parada): visibles en ≤ 60 s |

**Lo que el inventario no cachea a propósito:** la comprobación de stock de una salida (regla 2) lee siempre la base
(`available_stock`), y la ficha de un SKU (`GET /inventory/products/{id}`), que consultan los formularios antes de
enviar, tampoco pasa por la caché. Un listado desactualizado por otro proceso nunca deja registrar una salida sin stock
(test `test_products_exit_check_never_uses_the_cache`).

**Seguridad.** Los dos endpoints exigen JWT en su router. La dependencia se resuelve **antes** de ejecutar la función,
así que una petición sin token o con uno no válido responde 401 sin llegar a la caché (los tests comprueban que los
contadores no se mueven). Las respuestas no dependen de la identidad, el rol, la sesión ni el idioma: cualquier
usuario autenticado recibe exactamente los mismos bytes (test con un `user` y un `admin`). No hay paginación ni
ordenación configurables; el único parámetro (`warehouse`) forma parte de la clave.

**Instrumentación.** `RequestTimingMiddleware` es ASGI puro, va dentro de CORS y fuera del 500 genérico (registra el
estado final) y escribe en `trackflow.api.timing` una línea por petición:
`GET /inventory/products 200 7.34 ms sql=3`. La ruta es la plantilla (`/suppliers/{supplier_id}`) y una URL
desconocida se registra como `<sin ruta>`: nunca ids, query strings, cabeceras, cuerpos ni tokens. Con una excepción,
la línea se escribe igual (`try/finally`) a nivel ERROR con el tipo de error, sin su mensaje. `sql=` cuenta las
consultas con un listener `before_cursor_execute` del motor SQLModel y un `ContextVar` por petición.

## 6. Resultados comparativos

**Comparación principal: rondas alternas** (`results/interleaved.json`). 5 rondas, en cada una 10 peticiones de
calentamiento y 100 medidas por endpoint, alternando la API sin caché y la API con caché, que estaban arrancadas a la
vez sobre copias del mismo dataset. Latencia en el cliente.

| Endpoint | Mediana antes | Mediana después | Variación | Media antes → después | P95 antes → después |
| --- | ---: | ---: | ---: | ---: | ---: |
| `GET /api/incidents/summary` | 20,24 ms | 1,62 ms | −92,0 % | 29,72 → 1,93 ms | 61,29 → 3,07 ms |
| `GET /inventory/products` | 42,15 ms | 7,57 ms | −82,0 % | 57,17 → 9,95 ms | 120,55 → 19,53 ms |
| `GET /inventory/products?warehouse=LA` | 34,91 ms | 5,00 ms | −85,7 % | 37,55 → 5,77 ms | 50,02 → 7,58 ms |
| *Control* `GET /health` | 0,70 ms | 0,74 ms | +5,4 % | | |
| *Control* `GET /suppliers` | 7,80 ms | 7,92 ms | +1,6 % | | |
| *Control* `GET /api/incidents/{id}` | 15,82 ms | 15,61 ms | −1,3 % | | |
| *Control* `GET /inventory/products/{id}` | 3,38 ms | 3,28 ms | −2,8 % | | |

Los controles (mismo código en las dos APIs) se mueven ±5 %: ese es el ruido de la medición.

**Tabla del enunciado** (servidor, ejecución completa de `bench_api.py`, 200 peticiones; `results/before.json` y
`results/after.json`):

| Métrica | Antes | Después | Variación |
| --- | ---: | ---: | ---: |
| Latencia media — resumen / inventario / inventario LA | 22,37 / 45,67 / 35,81 ms | 1,51 / 7,89 / 5,50 ms | −93 % / −83 % / −85 % |
| Latencia mediana — ídem | 21,06 / 42,16 / 33,86 ms | 1,36 / 7,34 / 4,84 ms | −94 % / −83 % / −86 % |
| P95 — ídem | 27,42 / 81,56 / 42,72 ms | 2,23 / 8,67 / 6,64 ms | −92 % / −89 % / −84 % |
| Consultas SQL por petición — inventario | 3 | 0 en acierto, 3 en fallo | −100 % en acierto |
| Cache hit ratio, carga mixta (`results/workload.json`) — resumen / inventario | N/A (sin caché) | 86,8 % / 79,7 % | — |
| Con 8 hilos: pet./s — resumen / inventario / LA | 47,7 / 8,6 / 11,1 | 551,2 / 120,3 / 187,5 | ×11,6 / ×14,0 / ×16,9 |
| Con 8 hilos: p95 — ídem | 214,5 / 1.000,7 / 786,9 ms | 16,1 / 101,2 / 68,9 ms | −93 % / −90 % / −91 % |

En esa ejecución completa, la parte «antes» se midió con el equipo más cargado: los controles salieron hasta ×2 más
lentos que en la parte «después». Por eso la tabla anterior es la de referencia. Los endpoints cacheados dan cifras
coherentes en las tres mediciones (primera completa, segunda completa y rondas alternas).

**Comportamiento tras invalidar** (`workload.py`). 2.000 operaciones mezcladas: 90 % lecturas del listado (con y sin
almacén) y del resumen, 10 % escrituras que invalidan (entradas de stock, altas y cambios de estado). En proceso con
`TestClient`, que suma unos milisegundos fijos a cada petición.

| Caché | Aciertos | Fallos | Invalidaciones | Mediana acierto | Mediana fallo (incluye primeras lecturas tras escribir) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `incidents.summary` (60 s) | 584 | 89 | 104 | 5,1 ms | 37,4 ms |
| `inventory.products` (30 s) | 892 | 227 | 104 | 10,7 ms | 46,6 ms |

La primera lectura después de una escritura cuesta lo mismo que sin caché (no hay penalización por invalidar) y las
siguientes vuelven a ser aciertos. El inventario tiene más fallos porque tiene tres claves y un TTL más corto. La
proporción lecturas:escrituras es una *estimación*; con más escrituras, la tasa de aciertos baja.

**Consumo de recursos:** N/A. No se midió memoria ni CPU del proceso; el tamaño de lo guardado se acota en §5.

**Frontend** (`results/frontend-before.json` y `frontend-after.json`): ver las tablas de §4.

## 7. Frescura frente a rendimiento

**Caso aceptado: el listado de stock puede ir hasta 30 s por detrás de un cambio hecho fuera de la API.** Si el seed
del inventario, otro worker o una corrección hecha directamente en Supabase añaden un movimiento, `GET
/inventory/products` sigue mostrando el stock anterior hasta que caduca la entrada (test
`test_products_out_of_band_change_waits_for_the_ttl_but_the_detail_is_always_fresh`). Se acepta porque:

- todas las escrituras normales (formularios del backoffice) pasan por la API e invalidan al momento, así que en el
  uso diario no hay retraso;
- la decisión crítica (¿hay stock para esta salida?) nunca usa la caché: la ficha del SKU y la comprobación de la API
  leen la base;
- a cambio, el listado pasa de 42 a 7,6 ms, y de 8,6 a 120 peticiones/s con 8 usuarios a la vez.

**Por qué 30 s y no otro valor.** Más corto (5 s) apenas cambia la experiencia diaria, porque la invalidación ya
cubre las escrituras propias, pero multiplica los fallos cuando varias personas consultan el inventario. Más largo
(5 min) dejaría demasiado tiempo un stock que no cuadra con lo que ve quien trabaja directamente sobre la base. El
**resumen de incidencias usa 60 s** porque son totales para un panel, donde un minuto de desfase en un contador no
cambia ninguna decisión, y la única escritura externa (`seed_incidents.py`) se ejecuta con la API parada.

## 8. Qué no se cacheó y por qué

| Endpoint o componente | Motivo |
| --- | --- |
| `GET /suppliers` | **Implementado, medido y retirado.** Con 500 proveedores pasaba de 7,54 a 7,08 ms (−6 %), dentro del ruido de los controles. El coste estaba en validar y serializar 500 modelos, no en leer TinyDB, y la caché no se salta esa parte sin cambiar el contrato de las funciones del router (las pruebas API-042 las llaman directamente). Un riesgo de datos viejos sin beneficio no compensa. Test `test_suppliers_list_is_not_cached` |
| `GET /inventory/orders` | El más caro (1,1–1,5 s, 11,7 MB), pero cambia con cada movimiento y guardar 11,7 MB por entrada no es razonable. El problema real es que no tiene paginación (§10) |
| `GET /api/incidents` y sus filtros | 81 ms sin filtros (1,8 MB). Cambia con cada cambio de estado del gestor, cuatro filtros combinables darían cientos de claves de hasta 1,8 MB y el gestor ya actualiza la fila de forma optimista. Mismo problema de fondo: sin paginación |
| `GET /inventory/products/{id}` | Barato (3,4 ms) y los formularios lo usan para comprobar el stock justo antes de enviar: debe ser exacto |
| `GET /auth/me`, `GET /profiles/me`, `GET /users`, `GET /users/{id}` | Datos personales o que dependen del rol. Además, `get_current_user` relee el usuario en cada petición para que un usuario desactivado o con la contraseña cambiada pierda el acceso al momento: cachearlo rompería esa garantía |
| `POST /api/incidents/analyze`, `GET /api/incidents/results/export` | Escritura o cálculo por fichero subido; la exportación ya sirve el último análisis desde memoria |
| `GET /health` | Constante y < 1 ms; además debe reflejar si el proceso responde |
| `uis/website` | Sin componentes cliente pesados ni cálculos: no hay nada que diferir ni memoizar |

## 9. Seguridad y consistencia

- **Datos privados.** Solo se cachean dos respuestas idénticas para todo usuario autenticado. Nada que dependa de
  identidad, rol, sesión, preferencias o idioma; la autenticación no se cachea.
- **Aislamiento por usuario.** No hace falta separar por usuario porque las respuestas no varían entre usuarios
  (comprobado con dos roles). La caché nunca sustituye a la comprobación del JWT, que ocurre antes.
- **Permisos.** Ningún endpoint cacheado filtra por rol; si algún día lo hiciera, el rol tendría que entrar en la
  clave o habría que retirar la caché.
- **Invalidación.** Explícita y solo tras escrituras confirmadas (commit o escritura en TinyDB). Las rechazadas no
  invalidan. La generación evita guardar lecturas que se cruzan con una escritura.
- **Expiración.** TTL obligatorio y positivo (el constructor rechaza 0 o negativo): ninguna entrada vive para siempre.
- **Sin caché HTTP.** La API sigue sin enviar `Cache-Control` y las respuestas no llevan `Last-Modified`: ni
  navegadores ni proxies las guardan. No se ha añadido nada en ese nivel.
- **Limitaciones.** La caché es **por proceso**: con varios workers de uvicorn, cada uno tiene la suya y una escritura
  solo invalida la del worker que la atendió, así que los demás pueden servir datos viejos hasta el TTL (30/60 s). Hoy
  se despliega con un worker (`docs/despliegue-api.md`, Docker). Los cambios de otros procesos tardan hasta el TTL.
  Reiniciar la API vacía la caché.

## 10. Limitaciones y mejoras futuras

- **Paginación** de `GET /inventory/orders` (1,1 s, 11,7 MB) y de `GET /api/incidents` (1,8 MB). Es la mejora con
  más impacto pendiente, pero cambia el contrato y el backoffice.
- Si la API pasa a **varios workers o varias instancias**: invalidación compartida (Redis con pub/sub o una clave de
  versión en la base) o TTL más cortos. Hasta entonces, Redis no aporta nada.
- **Supabase:** repetir la medición con `DATABASE_URL` real. Cada consulta suma latencia de red, así que el ahorro por
  acierto debería ser mayor (no medido).
- **Formulario de proveedores en pantallas táctiles:** precargarlo cuando la página quede ociosa (`requestIdleCallback`)
  eliminaría la espera de ~0,5 s del clic inmediato, a cambio de descargar 2 KB que quizá no se usen.
- **Turbopack:** `npm run build` falla en este equipo al descargar Google Fonts (también en `main`); todas las
  mediciones del frontend usan `next build --webpack`.
- `React.memo` en las filas de los listados (`IncidentRow`) evitaría volver a renderizar toda la tabla en cada cambio de
  estado optimista. No se midió, así que no se aplicó.
