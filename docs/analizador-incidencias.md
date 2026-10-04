# Analizador de incidencias — TrackFlow

Herramienta interna para el equipo de atención al cliente (CX) de Valentina Cruz. Lee el CSV de incidencias exportado
del helpdesk, valida cada registro según [`CONTEXT-incidencias.es.md`](../CONTEXT-incidencias.es.md), excluye los
inválidos y calcula las métricas de volumen, categoría, estado, satisfacción y errores. Es una práctica del curso sin
número de hito (como el directorio de proveedores), por lo que no figura en [`hitos.md`](./hitos.md).

Funciona de dos formas que comparten exactamente la misma lógica:

- **Script de consola** ([`scripts/analyze.py`](../scripts/analyze.py)).
- **Backoffice web** (ruta `/incidencias` de [`uis/backoffice`](../uis/backoffice/README.md)) sobre la **API**
  [`services/api`](../services/api/README.md), la misma que sirve el directorio de proveedores.

Todo el procesamiento es local: el CSV contiene correos de clientes y no se envía a ningún servicio externo.

> Se construyó primero en un repositorio aparte (`analizador-incidencias`) y se integró después en este monorepo,
> adaptado a sus convenciones: API existente en lugar de una app nueva, `NEXT_PUBLIC_API_BASE_URL` + CORS en lugar de
> un proxy de Next.js, pruebas en navegador fuera del repo y capturas manuales.

## Estructura

```text
CONTEXT-incidencias.es.md          ← campos, reglas y valores esperados del CSV
packages/analisis-incidencias/     ← lógica compartida (solo biblioteca estándar de Python)
├── src/analisis_incidencias/      ← dominio · carga · validacion · metricas · exportacion
└── tests/                         ← 43 tests
scripts/
├── analyze.py                     ← CLI: informe en consola y exportación a results.csv
├── incidents-trackflow.csv        ← fichero de prueba (100 registros, datos ficticios)
└── tests/                         ← 27 tests (CLI y contrato con el CONTEXT)
services/api/                      ← FastAPI (proveedores + incidencias)
├── app/routes/incidents.py        ← POST /api/incidents/analyze · GET /api/incidents/results/export
└── tests/test_incidents.py        ← 26 tests
uis/backoffice/                    ← Next.js
├── app/incidencias/page.tsx       ← página "Análisis de incidencias"
├── components/incidencias/        ← selector de CSV, resultados, barras, tablas, inválidos
└── lib/incidencias.ts             ← subida (FormData) y descarga (blob) sobre lib/http.ts
```

```text
CSV ──► packages/analisis-incidencias ──┬──► scripts/analyze.py (consola + results.csv)
                                        └──► services/api ──(CORS)──► uis/backoffice (navegador)
```

## Requisitos

| Herramienta | Versión probada | Para qué |
| --- | --- | --- |
| Python | 3.14.6 (script y paquete: ≥ 3.11; API: ≥ 3.12) | script, paquete y API |
| uv | 0.12.19 | entorno y dependencias de la API |
| Node.js / npm | 24.19 / 11.17 (Node ≥ 20.9) | backoffice |

## Instalación

El script no necesita instalar nada. Para la API y el backoffice, desde la raíz del repo en Windows PowerShell (un
comando por línea):

```powershell
cd services\api
uv sync
cd ..\..\uis\backoffice
npm install
Copy-Item .env.example .env.local
```

`uv sync` crea `services/api/.venv` e instala FastAPI, Uvicorn, TinyDB, `python-multipart` y el paquete compartido
(dependencia local editable). `.env.local` contiene `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

## Ejecución

### Script

```powershell
cd scripts
python analyze.py incidents-trackflow.csv
```

- Argumento obligatorio: ruta al CSV. `-o/--output` cambia el fichero de exportación (por defecto `results.csv` en el
  directorio actual; `scripts/results.csv` está en `.gitignore`).
- Al terminar pregunta `¿Deseas exportar los resultados a CSV? [s / n]`. Acepta `s`, `sí`, `si`, `y`, `n`, `no`;
  ante otra respuesta vuelve a preguntar; con Ctrl+C o fin de entrada termina sin exportar.
- Códigos de salida: `0` correcto, `1` error de fichero (no existe, vacío, no UTF-8, columnas incorrectas), `2` falta
  el argumento.

### API

```powershell
cd services\api
uv run uvicorn app.main:app --reload --port 8000
```

Documentación interactiva en `http://localhost:8000/docs`. Comprobación: `http://localhost:8000/health`. Variable
opcional `CORS_ALLOWED_ORIGINS` (por defecto `http://localhost:3002,http://127.0.0.1:3002`, el backoffice).

### Backoffice

Con la API arrancada, en otra terminal:

```powershell
cd uis\backoffice
npm run dev
```

Abrir `http://localhost:3002/incidencias` (también desde el menú “Análisis de incidencias”). El navegador llama a la
API en la URL de `NEXT_PUBLIC_API_BASE_URL`, que Next.js incrusta al compilar: tras cambiarla, reinicia `npm run dev` o
repite `npm run build`. Si falta, la página muestra el aviso “Falta la variable NEXT_PUBLIC_API_BASE_URL…” en desarrollo
y “El servicio no está disponible en este momento…” en el build de producción.

## Formato del CSV

UTF-8 (con o sin BOM), separado por comas, con cabecera. Columnas obligatorias (definidas en el CONTEXT):
`incident_id, date, country, customer_type, tracking_number, carrier, category, description, status, customer_email,
satisfaction_score`. Las líneas en blanco se ignoran; se admiten columnas adicionales.

## Validación

Un registro es **inválido** si incumple al menos una regla. Los inválidos se cuentan, se clasifican por regla y se
listan (línea e `incident_id`, nunca el correo), pero no participan en las métricas.

| Regla | Condición | Origen |
| --- | --- | --- |
| País ausente o inválido | distinto de `US` / `ES` | CONTEXT |
| Transportista inválido para el país | vacío, desconocido o que no opera en el país (US: UPS, FEDEX, DHL_US · ES: MRW, SEUR, DHL_ES, LOCAL_ES) | CONTEXT |
| Número de seguimiento inválido | vacío o < 8 caracteres | CONTEXT |
| Categoría ausente o inválida | fuera de LOST_PARCEL, DELAYED_DELIVERY, WRONG_ADDRESS, RETURN_REQUEST, DAMAGE | CONTEXT |
| Descripción ausente o muy corta | < 5 caracteres | CONTEXT |
| Email ausente o inválido | vacío o sin `@` | CONTEXT |
| Cerrada sin puntuación | `status = CLOSED` sin `satisfaction_score` | CONTEXT |
| Puntuación fuera de rango | hay valor pero no es un entero de 1 a 5 | CONTEXT |
| ID de incidencia inválido | no sigue `TRF-` + 6 dígitos | complementaria |
| Fecha ausente o inválida | no es una fecha real `YYYY-MM-DD` | complementaria |
| Tipo de cliente inválido | distinto de `B2B` / `B2C` | complementaria |
| Estado ausente o inválido | distinto de `OPEN` / `CLOSED` / `DISCARDED` | complementaria |
| Número de columnas incorrecto | la fila no tiene las mismas columnas que la cabecera | complementaria |

Las reglas **complementarias** derivan de la tabla de campos obligatorios del CONTEXT (formato y valores permitidos),
no de su lista de reglas; con el fichero de prueba no marcan ningún registro.

Criterios:

- Un registro que incumple varias reglas cuenta **una vez** como inválido y aparece en **cada** regla del desglose.
- Si el país es inválido, solo se comprueba que el transportista exista (no se cuenta dos veces el mismo problema).
- Solo se eliminan espacios en los extremos; no se corrigen mayúsculas (`closed` es inválido).
- Una puntuación en una incidencia `OPEN` o `DISCARDED` no invalida el registro, pero no entra en el índice.

## Métricas (sobre registros válidos)

- Totales: procesados, válidos, inválidos.
- Por categoría, estado, país, tipo de cliente y transportista (conteo y porcentaje).
- Evolución temporal: por mes, trimestre, semana ISO y día de la semana.
- Cruces: país × categoría, transportista × categoría, transportista × estado.
- Satisfacción: incidencias cerradas con puntuación, media (2 decimales) y distribución 1–5; también por país,
  categoría y transportista.
- Errores: inválidos por regla y detalle por registro.

Con `scripts/incidents-trackflow.csv` se obtienen exactamente los valores esperados del CONTEXT:

| Métrica | Valor |
| --- | --- |
| Registros | 100 procesados · 95 válidos · 5 inválidos |
| Inválidos (1 por regla) | TRF-000003 seguimiento · TRF-000025 FEDEX en ES · TRF-000042 categoría vacía · TRF-000068 email sin @ · TRF-000097 CLOSED sin puntuación |
| Categorías | LOST_PARCEL 14 · DELAYED_DELIVERY 38 · WRONG_ADDRESS 19 · RETURN_REQUEST 17 · DAMAGE 7 |
| Estados | OPEN 29 · CLOSED 52 · DISCARDED 14 |
| Países | US 50 · ES 45 |
| Satisfacción | 52 de 52 cerradas con puntuación · media 3.06 · distribución 6 / 11 / 15 / 14 / 6 |
| Satisfacción por país | US 2.96 · ES 3.17 |

## Endpoints

| Método y ruta | Descripción |
| --- | --- |
| `POST /api/incidents/analyze` | `multipart/form-data` con el CSV en el campo `file`. Devuelve el resultado en JSON (`application/json; charset=utf-8`). |
| `GET /api/incidents/results/export` | Descarga el último análisis como `results.csv` (`text/csv; charset=utf-8`, `attachment`). |
| `GET /health` | Comprobación de estado de toda la API: `{"status": "ok"}`. |

Las rutas de incidencias llevan el prefijo `/api` porque así las pide el ejercicio; las del directorio de proveedores
(`/suppliers`) no lo llevan. Conviven en la misma app FastAPI.

La respuesta de `POST` contiene `archivo`, `totales`, `invalidos_por_regla`, `registros_invalidos`, `por_categoria`,
`por_estado`, `por_pais`, `por_tipo_cliente`, `por_transportista`, `por_fecha`, `cruces`, `satisfaccion` y `reglas`
(etiqueta legible de cada regla y si es complementaria, para que el frontend no las duplique). Es el mismo diccionario
que calcula el script.

Errores (siempre JSON `{"detail": "mensaje"}`, sin trazas):

| Código | Caso |
| --- | --- |
| 400 | no se envía fichero en el campo `file` |
| 404 | exportación sin ningún análisis previo |
| 413 | fichero mayor de 5 MB |
| 415 | el fichero no tiene extensión `.csv` |
| 422 | fichero vacío, solo cabecera, no UTF-8, CSV mal formado o columnas obligatorias ausentes |
| 500 | error inesperado al analizar o exportar: mensaje genérico `Error interno del servidor.`; la traza queda en el log |

El 500 se captura **solo en el router de incidencias**: el directorio de proveedores mantiene el comportamiento por
defecto de FastAPI.

El último análisis correcto se guarda **en memoria** (`app.state.ultimo_analisis`) mientras la API está en marcha, sin
base de datos. Un análisis fallido no lo sustituye.

CORS: los orígenes de `CORS_ALLOWED_ORIGINS` pueden llamar a la API desde el navegador, y la API expone la cabecera
`Content-Disposition` (`expose_headers`) para que la descarga del backoffice conserve el nombre `results.csv`.

## Exportación

`results.csv` tiene una fila por métrica con las columnas `seccion, metrica, valor, porcentaje` (UTF-8 con BOM, para que
Excel respete los acentos). El porcentaje es sobre el total de su grupo: registros válidos en los desgloses simples,
la fila en los cruces (p. ej. `UPS|LOST_PARCEL` sobre el total de UPS) e incidencias puntuadas en la distribución de
satisfacción. Solo contiene agregados: ni correos ni IDs. El script, la API y la descarga del backoffice generan **los
mismos bytes** (`generar_csv_bytes`).

## Backoffice

Página `/incidencias`, en este orden: selector del CSV (arrastrar o hacer clic) y botón **Analizar CSV** → aviso
“Análisis completado” con el botón **Descargar resultados CSV** → resumen general → por categoría → por estado →
satisfacción → registros inválidos → más desgloses → evolución temporal → cruces.

- Números en formato es-ES (`3,06`, `14,7 %`); barras de una serie en `blue-700`; aviso de inválidos en ámbar con icono
  y texto; tablas de satisfacción por país, categoría y transportista.
- Errores claros: sin fichero, extensión no `.csv` (sin llamar a la API), `detail` de la API, API que no responde
  (“No se pudo conectar con la API de TrackFlow…”), API que tarda más de 20 s, respuesta que no es JSON y variable
  `NEXT_PUBLIC_API_BASE_URL` ausente. Un 5xx muestra un texto fijo, nunca el detalle interno.
- Reutiliza `StatCard`, `PageSection` y `NavLink` del backoffice. Las llamadas usan `fetchApi` de `lib/http.ts` (URL
  base y conversión de errores compartidas con proveedores), que no fuerza `Content-Type: application/json` y así
  permite enviar `FormData` y descargar el CSV como blob.

## Pruebas

| Batería | Comando | Resultado |
| --- | --- | --- |
| Paquete + script | `python -m pytest scripts/tests packages/analisis-incidencias/tests` (desde la raíz) | 70 superados |
| API (proveedores + incidencias) | `uv run pytest -q` (desde `services/api`) | 144 superados (26 de incidencias) |
| Backoffice (calidad) | `npm run lint`, `npm run typecheck`, `npm run build` (desde `uis/backoffice`) | sin errores |
| Backoffice (navegador) | Edge + `playwright-core` fuera del repo, con la API y el backoffice arrancados | 19 superados |

Las apps JS del monorepo no tienen runner de tests: las pruebas en navegador se ejecutan fuera del repositorio (igual
que en el directorio de proveedores) y sus resultados se registran en
[`pruebas-analizador-incidencias.md`](./pruebas-analizador-incidencias.md).

## Capturas

Tomadas por el desarrollador en local con el CSV de prueba:

| Captura | Contenido |
| --- | --- |
| `scripts/screenshots/screenshot script consola1-3.png` ([1](../scripts/screenshots/screenshot%20script%20consola1.png), [2](../scripts/screenshots/screenshot%20script%20consola2.png), [3](../scripts/screenshots/screenshot%20script%20consola3.png)) | Salida completa de `python analyze.py incidents-trackflow.csv` en PowerShell, respondiendo `s` a la exportación. |
| [`uis/backoffice/screenshots/screenshot incidencias resumen.png`](../uis/backoffice/screenshots/screenshot%20incidencias%20resumen.png) | `/incidencias` con el CSV analizado: resumen general. |
| [`uis/backoffice/screenshots/screenshot incidencias invalidos.png`](../uis/backoffice/screenshots/screenshot%20incidencias%20invalidos.png) | Sección de registros inválidos (reglas y detalle por línea e ID). |
| [`uis/backoffice/screenshots/screenshot incidencias completo.png`](../uis/backoffice/screenshots/screenshot%20incidencias%20completo.png) | Página completa del análisis. |
| [`services/api/screenshots/screenshot incidencias analyze.png`](../services/api/screenshots/screenshot%20incidencias%20analyze.png) | `POST /api/incidents/analyze` en Swagger UI con el CSV de prueba: 200, JSON UTF-8 y `Content-Disposition` expuesto por CORS. |

## Seguridad y datos sensibles

- Sin servicios externos: el paquete solo usa la biblioteca estándar; la API, FastAPI/Uvicorn.
- `customer_email` nunca se imprime, registra, devuelve ni exporta (hay tests que lo comprueban en consola, JSON,
  log, exportación y página web). Los inválidos se identifican por número de línea e `incident_id`.
- El log de la API registra la petición HTTP (uvicorn) y una línea de resumen por análisis del logger
  `trackflow.api.incidents` (nombre de fichero y totales).
- La API **no tiene autenticación**: solo para uso local (ver [`services/api`](../services/api/README.md)).
- `scripts/incidents-trackflow.csv` se versiona: son datos ficticios del ejercicio.

## Decisiones técnicas

| Decisión | Motivo |
| --- | --- |
| Python estándar, sin pandas | 100 filas y conteos simples: sin dependencias y con traza por registro de las reglas incumplidas. |
| Lógica en `packages/analisis-incidencias` | Regla del monorepo: el código usado por 2+ carpetas va en `packages/`. El script la importa desde `src/` sin instalarla; la API la instala como dependencia editable con `uv` (`[tool.uv.sources]`). |
| Endpoints en la API existente (`services/api`) | Un único servicio FastAPI para el backoffice; el analizador no necesita una app aparte. |
| Rutas `/api/incidents/...` | Las exige el ejercicio, aunque proveedores use `/suppliers` sin prefijo. |
| 500 capturado solo en el router | Un manejador global cambiaría las respuestas de proveedores. |
| Logger `trackflow` a INFO con handler propio | Muestra la línea de resumen en la salida de uvicorn sin tocar el logger raíz. |
| Último resultado en memoria | El ejercicio no necesita persistencia; evita una base de datos. Exige **un solo proceso** de la API. |
| Backoffice → API con `NEXT_PUBLIC_API_BASE_URL` + CORS (`expose_headers`) | Mismo patrón que proveedores; sin el proxy `rewrites` de la fuente. |
| `fetchApi` en `lib/http.ts` | Reutiliza URL base y errores sin forzar JSON, necesario para `FormData` y la descarga del CSV. |
| Pruebas en navegador fuera del repo | Las apps JS no tienen runner de tests; no se añade `playwright-core` al backoffice. |
| Salida en español | Decisión del equipo; los códigos de categoría, estado, país y transportista se muestran tal como los define el CONTEXT. |
| Reglas complementarias | Validan campos obligatorios que la lista de reglas del CONTEXT no cubre, sin alterar los valores esperados. |

## Limitaciones conocidas

- El último análisis se pierde al reiniciar la API y es compartido por todos los usuarios; con varios workers la
  exportación podría no encontrarlo.
- El CONTEXT menciona “1,000 filas”, una ruta `incidents-analysis/…` y una salida de ejemplo en inglés; se toman como
  referencia la tabla de valores esperados (100 filas) y la decisión de salida en español.
- El mensaje de `argparse` cuando falta el argumento está en inglés (lo genera la biblioteca estándar).
- En Windows, si la salida de la API se redirige a un fichero, las tildes del log se escriben en cp1252.
- Excel en configuración regional española puede esperar `;` como separador al abrir el CSV con doble clic; se
  mantiene la coma que define el CONTEXT.
- En producción el backoffice no tiene la API (solo local), así que `/incidencias` muestra el aviso de variable no
  configurada, igual que `/proveedores`.

## Despliegue

No ejecutado. Instrucciones para el agente del servidor (tarball con `services/api` **y**
`packages/analisis-incidencias`, `uv sync --locked --no-dev`, un solo worker, variables, tamaño de subida en el proxy,
autenticación antes de publicar y verificación): [`despliegue-api.md`](./despliegue-api.md).
