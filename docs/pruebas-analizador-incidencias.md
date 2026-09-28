# Registro de pruebas — Analizador de incidencias

Ejecución en el monorepo tras la integración (rama `feature/analizador-incidencias`), 2026-09-28 · Windows 11 ·
Python 3.14.6 · uv 0.12.19 · Node 24.19 · Microsoft Edge (`playwright-core` 1.63 fuera del repo).
Todas las pruebas se han ejecutado; ninguna se marca PASS sin ejecutarse. Documentación del analizador:
[`analizador-incidencias.md`](./analizador-incidencias.md).

| Batería | Comando | Resultado |
| --- | --- | --- |
| Paquete + script | `python -m pytest scripts/tests packages/analisis-incidencias/tests` (desde la raíz) | 70 passed (43 + 27) |
| API | `cd services\api` · `uv run pytest -q -W error::DeprecationWarning` | 144 passed (118 proveedores + 26 incidencias) |
| Dependencias de la API | `uv lock --check` | OK |
| Backoffice | `npm run lint` · `npm run typecheck` · `npm run build` | sin errores; `/incidencias` estática |
| Rutas del backoffice | `check-route.mjs` sobre `/`, `/proveedores` y `/incidencias` (`npm run start`) | 200 en las tres |
| Backoffice en navegador | `node --test` con Edge + `playwright-core` (scratchpad), API y backoffice arrancados | 19 passed |

## Script (`scripts/analyze.py` + paquete compartido)

| Prueba | Entrada | Acción | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- | --- |
| CSV válido | CSV con registros correctos | `analizar()` | 0 inválidos, métricas calculadas | 0 inválidos (`test_registro_valido_no_tiene_errores`, `test_puntuacion_en_incidencia_abierta_es_valida_pero_no_cuenta`) | PASS |
| CSV con inválidos | `incidents-trackflow.csv` | `python analyze.py incidents-trackflow.csv` | 100 / 95 / 5 y valores del CONTEXT | 100 / 95 / 5; inválidos en las líneas 4, 26, 43, 69 y 98 (TRF-000003, 025, 042, 068, 097); categorías 14/38/19/17/7; estados 29/52/14; países 50/45; media 3.06; 6/11/15/14/6; US 2.96 · ES 3.17 | PASS |
| Igual que el script original | CSV real | comparar con `analizador-incidencias/scripts/analyze.py` | misma salida y exportación | consola igual (salvo la ruta de exportación); `results.csv` idéntico byte a byte | PASS |
| Campo obligatorio ausente o mal formado | `country`, `carrier`, `tracking_number`, `category`, `customer_email` vacíos; `description`, `date`, `incident_id` con formato inválido | `validar_registro()` | regla correspondiente | regla correspondiente en cada caso (`test_cada_regla_se_detecta`) | PASS |
| Estado inválido | `status = PENDING` / `closed` | `validar_registro()` | `estado_invalido` | `estado_invalido` | PASS |
| Puntuación | `CLOSED` sin puntuación; 0, 6, 3.5, abc; `OPEN` con 1 | `validar_registro()` / `analizar()` | `cerrada_sin_puntuacion`; `puntuacion_fuera_rango`; válida sin contar | según lo esperado | PASS |
| Varias reglas en un registro | categoría vacía + email sin @ | `analizar()` | 1 inválido, cuenta en 2 reglas | 1 inválido, 2 reglas | PASS |
| Exportación | respuesta no válida y después `s` | pregunta de exportación | repite y exporta `results.csv` | repite con aviso; exporta con BOM UTF-8 | PASS |
| Sin exportar | `n` / fin de entrada | pregunta de exportación | termina sin fichero, salida 0 | sin `results.csv`, salida 0 | PASS |
| Errores de uso | fichero inexistente / sin argumento | CLI | salida 1 / 2 | “Error: El fichero no existe…”, 1 / uso de argparse, 2 | PASS |
| Windows PowerShell 5.1 | CSV real | `"n" \| python analyze.py …` | acentos y caracteres de caja correctos | correctos, salida 0 | PASS |
| Privacidad | CSV real | informe + exportación | ningún correo | 0 `@` en consola y en `results.csv` | PASS |

## API (`services/api`)

| Prueba | Entrada | Acción | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- | --- |
| POST correcto | `incidents-trackflow.csv` | `POST /api/incidents/analyze` | 200 y valores del CONTEXT | 200 `application/json; charset=utf-8`; todos los valores; sin `@` | PASS |
| Equivalencia con el script | CSV real | comparar JSON con `analizar()` del script | idéntico | idéntico | PASS |
| Fichero no enviado | sin campo `file` / otro campo | POST | 400 | 400 “No se ha enviado ningún fichero…” | PASS |
| Formato no admitido | `.xlsx` | POST | 415 | 415 “…extensión .csv.” | PASS |
| Contenido no procesable | vacío, solo cabecera, columnas ausentes, latin-1 | POST | 422 | 422 con el mensaje de cada caso | PASS |
| Fichero demasiado grande | 5 MB + 1 byte (servidor real); límite reducido (test) | POST | 413 | 413 “…tamaño máximo de 5 MB.” | PASS |
| Error inesperado | `analizar` / `generar_csv_bytes` forzados a fallar | POST / GET | 500 sin traza; traza en el log | 500 `{"detail": "Error interno del servidor."}`; traza en el log | PASS |
| Exportación | tras analizar el CSV real | `GET /api/incidents/results/export` | CSV descargable | 200, `text/csv; charset=utf-8`, `attachment; filename="results.csv"` | PASS |
| Exportación = script | CSV real | comparar con `results.csv` del script | mismos bytes | idéntico byte a byte (test y servidor real) | PASS |
| Exportación antes de analizar | API recién arrancada | GET | 404 | 404 “Todavía no se ha analizado ningún fichero…” | PASS |
| Análisis fallido conserva el anterior | CSV real y después CSV vacío | POST, POST, GET | exporta el primero | exporta 100 registros | PASS |
| CORS | origen `localhost:3002` / otro | preflight `OPTIONS` | permitido / rechazado | permitido / sin `access-control-allow-origin` | PASS |
| CORS de la descarga | GET con origen `localhost:3002` | export | `Access-Control-Expose-Headers: Content-Disposition` | presente | PASS |
| Log sin correos | CSV real | POST | resumen sin datos personales | `Análisis de 'incidents-trackflow.csv': 100 registros (95 válidos, 5 inválidos)`, 0 `@` | PASS |
| Regresión de proveedores | — | 118 tests; `GET /suppliers?country=Spain`; preflight `PATCH` | sin cambios | 118 passed; 200 con 6; preflight permitido | PASS |
| Pruebas de mutación | quitar `expose_headers` / quitar el `except` del router | `uv run pytest` | fallan sus tests | falla 1 test en cada caso; restaurado → 144 | PASS |

## Backoffice (`uis/backoffice`, Edge)

API real en `:8000` (sobre una copia de la base de proveedores) y backoffice con `npm run start` en `:3002`.

| Prueba | Entrada | Acción | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- | --- |
| Navegación | — | clic en “Análisis de incidencias” | abre `/incidencias` y marca el enlace activo | `/incidencias`, `aria-current="page"`, título de la página | PASS |
| Sin fichero | — | clic en “Analizar CSV” | aviso | “Selecciona un fichero CSV antes de analizar.” | PASS |
| Fichero no CSV | `datos.txt` | seleccionar y analizar | aviso sin llamar a la API | “…extensión .csv.”; 0 peticiones a la API | PASS |
| Error de la API | CSV vacío | analizar | `detail` de la API | “El fichero está vacío.” | PASS |
| Carga | CSV real, respuesta retrasada 1 s | analizar | “Analizando…” deshabilitado | deshabilitado | PASS |
| Petición a la API | CSV real | analizar | `multipart/form-data` a `NEXT_PUBLIC_API_BASE_URL` | `POST http://localhost:8000/api/incidents/analyze`, `boundary`, `archivo` correcto | PASS |
| Resultado correcto | CSV real | analizar | valores del CONTEXT en es-ES | 100 / 95 / 5 / 3,06 / 52 de 52; 14/38/19/17/7 con %; 29/52/14; 6/11/15/14/6; US 2,96 · ES 3,17 | PASS |
| Registros inválidos | CSV real | analizar | 5 registros con línea, ID y motivo; sin correos | 5 IDs; 0 `@` en la página | PASS |
| Orden y resto de secciones | CSV real | analizar | orden acordado; cruces y semanas | resumen → categoría → estado → satisfacción → inválidos → desgloses → temporal → cruces; `DHL_US 6 2 4 4 0 16`; `Semana 2 (08/01–14/01) 31` | PASS |
| Descarga | CSV real | “Descargar resultados CSV” | `results.csv` igual al del script | nombre `results.csv`; idéntico byte a byte | PASS |
| Nombre desde la API | CSV real | `fetch` de la exportación en el navegador | `Content-Disposition` legible | `attachment; filename="results.csv"` | PASS |
| API caída | conexión rechazada (simulada) | analizar | mensaje de conexión | “No se pudo conectar con la API de TrackFlow (http://localhost:8000)…” | PASS |
| Error 500 | respuesta 500 simulada | analizar | `detail` | “Error interno del servidor.” | PASS |
| Descarga sin análisis en la API | 404 simulado | descargar | mensaje del 404 | “Todavía no se ha analizado ningún fichero…” | PASS |
| Móvil | 390 px | analizar | sin scroll horizontal; menú móvil marca la página | `scrollWidth` ≤ 390; enlace activo | PASS |
| Sin `NEXT_PUBLIC_API_BASE_URL` | build sin la variable | analizar | aviso claro, sin peticiones | “Falta la variable NEXT_PUBLIC_API_BASE_URL…”; 0 peticiones | PASS |
| Regresión `/proveedores` | — | abrir; suspender y reactivar un proveedor | 15 filas; `PATCH` JSON | 15 filas, menú activo; `PATCH` `application/json`; estado restaurado | PASS |
| Regresión `/` | — | abrir | resumen; anclas sin `aria-current` | correcto | PASS |
| Consola del navegador | flujos sin fallos simulados | — | sin errores | 0 | PASS |
