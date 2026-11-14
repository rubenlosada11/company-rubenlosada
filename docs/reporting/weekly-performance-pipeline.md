# Pipeline de desempeño semanal — Implementación, operación y verificación

> Reporte Semanal de Desempeño por Almacén y Cliente (práctica sin número de hito). El diseño, escrito antes del
> código, está en [`data/pipelines/PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md); este documento cuenta
> cómo quedó, cómo se ejecuta y cómo se ha comprobado. BRIEFING:
> [`CONTEXT-datapipelines.es.md`](../../CONTEXT-datapipelines.es.md).
>
> **Parte 2 (2026-11-13):** el pipeline se orquesta con **Prefect 3** y su código se movió a `data/` (PIPELINE_DESIGN
> §18). Las secciones 1–3 describen el estado actual; las de verificación (§5 y siguientes) recogen también lo que se
> comprobó en la Parte 1, con el código de entonces.

## 1. Qué hay y dónde

| Pieza | Fichero |
| --- | --- |
| Migración del esquema `reporting` (tabla del reporte + registro de ejecuciones) | [`services/api/migrations/20261113120000_reporting_weekly_performance.sql`](../../services/api/migrations/20261113120000_reporting_weekly_performance.sql) |
| **Flows y tasks de Prefect + línea de comandos** (`python data/pipelines/pipeline.py`) | [`data/pipelines/pipeline.py`](../../data/pipelines/pipeline.py) |
| extract (`telemetry_events`, `READ ONLY`) | [`data/pipelines/weekly_performance/extract.py`](../../data/pipelines/weekly_performance/extract.py) |
| observe (salud del origen y cobertura frente al inventario) | [`data/pipelines/weekly_performance/observe.py`](../../data/pipelines/weekly_performance/observe.py) |
| load (upsert + reconciliación, `run_id`, cambios por semana) | [`data/pipelines/weekly_performance/load.py`](../../data/pipelines/weekly_performance/load.py) |
| Snapshot de evaluación (`data/eval/weekly_performance/`) | [`data/pipelines/weekly_performance/evaluation.py`](../../data/pipelines/weekly_performance/evaluation.py) |
| Transformaciones puras: eventos, validate, aggregate, transform (coherencia, huella, versión) | [`data/process/weekly_performance/`](../../data/process/weekly_performance/) |
| Semanas ISO en UTC y ventana | [`app/reporting/weeks.py`](../../services/api/app/reporting/weeks.py) |
| Tablas de `reporting` y errores transitorios | [`app/reporting/tables.py`](../../services/api/app/reporting/tables.py) |
| Registro de ejecuciones | [`app/reporting/runs.py`](../../services/api/app/reporting/runs.py) |
| Puente API → flow (importación perezosa) | [`app/reporting/runner.py`](../../services/api/app/reporting/runner.py) |
| Endpoints `/reporting` | [`app/routes/reporting.py`](../../services/api/app/routes/reporting.py) |
| Tests | [`services/api/tests/reporting/`](../../services/api/tests/reporting/) |

`services/reporting/` del BRIEFING = `services/api/app/reporting/` en este repo (misma API que la telemetría; ver
PIPELINE_DESIGN §5): solo HTTP, lecturas y registro. El ETL está en `data/` y la API lo **importa**. No se ha tocado
`app/telemetry/analysis.py` ni `GET /telemetry/report`. Dependencia nueva: `prefect` (Parte 2).

## 2. Cómo funciona una ejecución

```text
POST /reporting/pipeline-runs        ─┐
python data/pipelines/pipeline.py    ─┴─► run_weekly_performance → flow de Prefect weekly-warehouse-client-performance
    1. resolve_window: semanas completas (por defecto, las 2 últimas)   → 422 / código 2 (sin crear flow run)
    2. register-run   fila `running` (id = id del flow run de Prefect)   → 409 si ya hay otra (también entre procesos)
    3. extract-telemetry-events  SELECT 4 event_type, entorno, [inicio, fin) (READ ONLY) + huella  phase = extracted
                                 reintentos: 3 (2/10/30 s) solo ante fallos transitorios
    4. transform-weekly-kpis     validate → aggregate → coherencia; CACHEADA                       phase = aggregated
    5. observe-source            OPCIONAL (return_state): si falla → aviso + ejecución parcial
    6. load-weekly-kpis          CRÍTICA (return_state): upsert + reconciliación en una transacción;
                                 reintentos: 2 (5/15 s) transitorios; si falla → `failed`, nada escrito
    7. write-eval-snapshot       OPCIONAL (return_state): JSON en data/eval/weekly_performance/
    8. close-run      `succeeded` (stats.outcome = succeeded | partial), phase = loaded, recuentos y stats
```

Un `POST` sin cuerpo, o el `cron` del lunes, recalcula las **2 últimas semanas completas**: la de la semana pasada y
la anterior, para recoger eventos tardíos y rellenar la semana de una ejecución que hubiera fallado.

## 3. Puesta en marcha

### 3.1. Supabase (una vez)

En el SQL Editor de Supabase, pegar y ejecutar el contenido de
`services/api/migrations/20261113120000_reporting_weekly_performance.sql` (idempotente; necesita la migración de
telemetría aplicada antes). Sin ella, con `DATABASE_URL` apuntando a Supabase, `POST /reporting/pipeline-runs`
responde 503 y el resto de la API funciona igual.

**Hecho el 2026-11-13** por el desarrollador, con una primera ejecución por línea de comandos: `succeeded`, fase
`loaded`, ventana 26-oct → 8-nov, 0 eventos y 0 filas, avisos `no_events_in_window` y `capture_gap` (esas semanas son
anteriores a la captura y el inventario sí tiene órdenes). Es el resultado esperado.

En SQLite (sin `DATABASE_URL`) no hace falta nada: las tablas se crean al primer uso.

### 3.2. Comandos (Windows PowerShell 5.1, desde la raíz del monorepo)

```powershell
uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py
uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py --week-start 2026-11-02 --weeks 4
uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py --dry-run
```

O con el entorno virtual de la API activado (`services\api\.venv\Scripts\Activate.ps1`) y `DATABASE_URL` en el
entorno: `python data/pipelines/pipeline.py`. Sin `DATABASE_URL`, el pipeline usa la base SQLite local de la API; la
primera línea de la salida dice qué base usa (sin credenciales). Prefect no necesita ningún servidor: arranca uno
temporal (~10–20 s) y lo para al terminar. Las ejecuciones parciales terminan con código 0 y el aviso
«Etapas opcionales con fallo».

- Sin parámetros: las 2 últimas semanas completas. `--week-start` es la semana más reciente (un lunes ya terminado);
  `--weeks`, cuántas hacia atrás (1–53).
- `--dry-run` ejecuta el flow `weekly-warehouse-client-performance-preview` (extract → transform → observe) y
  muestra las filas en JSON **sin escribir nada** ni registrar la ejecución: sirve para revisar datos reales antes de
  cargarlos.
- Códigos de salida: 0 bien, 1 la ejecución falló, 2 parámetros no válidos o ejecución ya en curso.
- Entorno de los eventos: `TELEMETRY_ENVIRONMENT` (por defecto `development`).

### 3.3. Programación semanal (aplazada: no forma parte de la entrega)

Lunes a las 06:00 UTC, en el `crontab` del VPS, con el contenedor de la API levantado:

```text
0 6 * * 1  cd /opt/company-rubenlosada && docker compose -f docker-compose.prod.yml exec -T backend python data/pipelines/pipeline.py
```

(Con Prefect, la imagen del backend tendrá que incluir `data/` y la ruta del comando, ajustarse al `WORKDIR`; hoy la
imagen solo copia `services/api/`: ver PIPELINE_DESIGN §18.10.)

**Decisión (2026-11-13): no se instala ahora.** La entrega del BRIEFING es diseñar, construir y probar el pipeline;
la programación queda diseñada y lista (la línea de arriba). Instalarla hoy no aportaría datos: el stack del VPS está
parado, sus imágenes (`infra40-rc1`) son anteriores a la telemetría y a este pipeline, su API no apunta a Supabase y
nadie usa esa instancia, así que calcularía cada lunes un reporte vacío. Se instalará cuando el backend se despliegue
de verdad con las imágenes nuevas y `DATABASE_URL` de producción (o desde un futuro workflow de `workflows/`, que
puede llamar a `POST /reporting/pipeline-runs`).

Mientras tanto, la ejecución se lanza a mano con `POST /reporting/pipeline-runs` o con la línea de comandos. Como la
ventana es de 2 semanas, una semana olvidada se recupera en la siguiente ejecución.

## 4. Endpoints

| Endpoint | Acceso | Respuestas |
| --- | --- | --- |
| `GET /reporting/weekly-warehouse-client-performance?week_start=YYYY-MM-DD` | Autenticado | 200 (también con `entries: []` si la semana se calculó sin actividad) · 401 · 404 (semana que ninguna corrida correcta ha calculado) · 422 (no es un lunes) · 503 |
| `GET /reporting/pipeline-runs/latest` | Autenticado | 200 · 401 · 404 (nunca ejecutado) · 503 |
| `POST /reporting/pipeline-runs` con `{"week_start"?, "weeks"?}` o sin cuerpo | `admin` o `manager` | 201 · 401 · 403 · 409 (otra en curso, de cualquier proceso) · 422 · 503 (falló; queda `failed`) |

Respuesta real del reporte (API local con una base desechable, 2026-11-13; desde la revisión lleva también `run_id`,
el de la corrida que calculó la semana):

```json
{
  "week_start": "2026-11-02",
  "computed_at": "2026-11-13T18:07:28.426296Z",
  "entries": [
    {"warehouse": "los_angeles", "client_id": "fashion-co", "inbound_units_count": 200, "outbound_orders_count": 8,
     "stockout_events_count": 1, "discrepancy_events_count": 1, "discrepancy_rate": 0.125},
    {"warehouse": "zaragoza", "client_id": "electro-brand", "inbound_units_count": 0, "outbound_orders_count": 1,
     "stockout_events_count": 0, "discrepancy_events_count": 0, "discrepancy_rate": 0.0}
  ]
}
```

Es el JSON del BRIEFING más `computed_at` y `run_id`. `discrepancy_rate` lleva 4 decimales (2 / 980 → `0.002`, como en el
ejemplo del BRIEFING). La respuesta de `pipeline-runs/latest` incluye la ventana (`week_from`, `week_to`), `phase`, `request_id`, tiempos,
`events_read`, `events_rejected`, `rows_upserted`, `rows_deleted`, `error` y `stats`:

| Clave de `stats` | Para qué sirve |
| --- | --- |
| `events_read`, `events_rejected` | Cuántos eventos de cada tipo se leyeron y cuáles se descartaron y por qué |
| `changes` | Por semana: filas insertadas, actualizadas, sin cambios y eliminadas (qué semanas publicadas corrigió) |
| `warnings` | `no_events_in_window` (probable captura caída), `silent_days`, `capture_gap`, `observability_unavailable` |
| `source_health` | Eventos de cualquier tipo y sesiones distintas por día; días sin ningún evento |
| `capture_coverage` | Por semana y almacén: órdenes del inventario frente a eventos capturados (entrada y salida) |

## 5. Cómo leer el reporte (para Thomas y Ana)

- **Una fila = un almacén + un cliente + una semana (lunes a domingo, UTC).** Los clientes sin actividad esa semana no
  aparecen.
- `inbound_units_count` son **unidades** recibidas; `outbound_orders_count` son **pedidos** despachados (no unidades).
- `discrepancy_rate` es discrepancias / pedidos. Puede pasar de 1 (más discrepancias que pedidos) y vale 0 si no hubo
  pedidos: mirar siempre `discrepancy_events_count` al lado.
- **Hoy `stockout_events_count` y `discrepancy_events_count` siempre valen 0 porque no se miden**: no hay mínimos de
  stock por cliente ni proceso de conteo físico (PIPELINE_DESIGN §4.1). `stats.events_read` de la última ejecución lo
  confirma (0 eventos de esos tipos leídos). El día que se emitan, el reporte los recoge sin cambiar el pipeline.
- **Antes de fiarse de una semana, mirar los `warnings` de su corrida.** `capture_gap` significa que el inventario
  tiene órdenes que la telemetría no capturó (o al revés): las cifras de esa semana se quedan cortas (o se pasan).
  `no_events_in_window` significa que no llegó ningún evento de ningún tipo: un reporte vacío no es «semana sin
  actividad», es «no sabemos».

## 6. Verificación (2026-11-13)

| Comprobación | Resultado |
| --- | --- |
| Tests de la API (`uv run pytest -q`) | **1647 passed, 4 skipped** (antes 1536; +111: 108 de `tests/reporting/` y 3 rutas nuevas en la auditoría de serialización). Los 4 saltados son los de PostgreSQL, que necesitan `REPORTING_TEST_DATABASE_URL` |
| Migración en PostgreSQL 16 local (pgserver, roles de Supabase simulados) | Aplicada **dos veces** sin error; 10 columnas idénticas al BRIEFING; `unique` y checks rechazan duplicado (23505), martes, almacén y contador negativo (23514); `anon`/`authenticated` sin acceso (42501); `service_role` solo `SELECT` |
| `tests/reporting/test_postgres.py` contra ese PostgreSQL | **4 passed** (dos veces): upsert que conserva `id`, reconciliación con `tuple NOT IN`, extracción en `READ ONLY` (una escritura falla con SQLSTATE 25006) y endpoints |
| Supabase real, solo lectura (`--dry-run` y SQL independiente, transacciones `READ ONLY`) | 83 filas en `telemetry_events`; 4 eventos de órdenes en `development`, todos en la semana en curso (2026-11-09). Ventana por defecto (26-oct → 8-nov): 0 eventos, 0 filas. Calculando esa semana solo para contrastar: 2 filas (`los_angeles/soundwave-electronics` 3 uds · 1 pedido; `zaragoza/purestep-footwear` 4 uds · 1 pedido), **idénticas** a un `GROUP BY` SQL escrito aparte; `telemetry_events` sin cambios. El esquema `reporting` aún no existe en Supabase |
| API arrancada (`uvicorn`, puerto 8010, base SQLite desechable) | `/health` 200; sin token 401; antes de ejecutar 404 y 404; `POST` como `user` 403; semana en curso 422; `POST` como `manager` 201 (13 eventos, 2 filas, 46 ms) y repetido 201 (mismas filas); reporte 200 (JSON de arriba); martes 422; `latest` 200; las 3 rutas en OpenAPI; sin errores en el log |
| Línea de comandos sobre la misma base | Ejecución `succeeded` (código 0), martes → código 2, `--dry-run --weeks 1` muestra las filas sin escribir |
| `ruff check` / `ruff format` (líneas de 120) sobre los ficheros nuevos | Sin avisos |

**Revisión (preguntas de diseño, PIPELINE_DESIGN §17), 2026-11-13:**

| Comprobación | Resultado |
| --- | --- |
| Tests de la API | **1659 passed, 6 skipped** (+12 de `tests/reporting/`: 8 de `observe`, 2 del flow y 2 de endpoints; los 6 saltados son los de PostgreSQL) |
| Migración modificada en un PostgreSQL 16 nuevo | Aplicada dos veces; `run_id` en la tabla del reporte, `request_id` y `phase` (con su check) en `pipeline_runs` e índice `pipeline_runs_one_running_idx`; mismas restricciones y permisos que antes |
| `test_postgres.py` | **6 passed** (dos veces): además de lo anterior, el índice parcial bloquea una segunda corrida `running` y las filas guardan su `run_id` |
| Supabase, solo lectura (`observe` sobre datos reales) | Ventana por defecto (26-oct → 8-nov): **0 eventos de telemetría pero 9 órdenes en el inventario** (7 de entrada y 2 despachos en la semana del 26-oct) → `no_events_in_window` + `capture_gap`: la captura aún no existía y un reporte vacío habría parecido una semana sin actividad. Semana en curso (solo contraste): 83 eventos en 2 días con 4 y 3 sesiones; Los Ángeles tiene 2 órdenes de entrada y 1 evento → `capture_gap` (una medición perdida) |

Los scripts de esta verificación (servidor PostgreSQL desechable, comprobación de la migración y lectura de Supabase)
quedaron fuera del repositorio; el test de PostgreSQL sí está versionado y se puede repetir:

```powershell
$env:REPORTING_TEST_DATABASE_URL = "postgresql+psycopg://postgres:@127.0.0.1:5432/postgres"
uv run pytest tests/reporting/test_postgres.py
```

(solo admite `localhost`/`127.0.0.1`, con las dos migraciones aplicadas: vacía las tablas de `reporting`).

### 6.1. Capturas

El desarrollador las hizo en local el 2026-11-13. Usó la API con su `.env` contra Supabase (con la migración ya
aplicada) y Swagger con un usuario `admin`. Están en
[`docs/screenshots/weekly-performance-pipeline/`](../screenshots/weekly-performance-pipeline/). Las semanas
completas de la ventana (26-oct → 8-nov) son anteriores a la captura de telemetría, así que el reporte sale vacío y
con avisos. Es el resultado esperado (§6).

| Captura | Qué muestra |
| --- | --- |
| [Ejecución por la API](../screenshots/weekly-performance-pipeline/01-swagger-post-pipeline-run.png) | El log de `POST /reporting/pipeline-runs`. Muestra el inicio de la corrida (`api`, `development`, su `request` y las semanas del 26-oct y del 2-nov), el extract de 0 eventos, los avisos de `observe` (`no_events_in_window`, `capture_gap`), los cambios por semana del load y la respuesta 201. Antes hay dos intentos rechazados con 422 por la validación del cuerpo |
| [Última corrida](../screenshots/weekly-performance-pipeline/02-swagger-latest-run.png) | El log de `GET /reporting/pipeline-runs/latest`: 200, con una sola consulta SQL |
| [Reporte semanal: log](../screenshots/weekly-performance-pipeline/03-swagger-weekly-report-a.png) | El log de `GET /reporting/weekly-warehouse-client-performance` sin parámetros: 200 |
| [Reporte semanal: respuesta](../screenshots/weekly-performance-pipeline/03-swagger-weekly-report-b.png) | La última semana calculada (`2026-11-02`), con `computed_at`, el `run_id` de la corrida de la captura 01 y `entries: []`: se calculó y no tuvo actividad. Debajo, los códigos documentados (401, 404, 422, 503) |
| [Semana no calculada: log](../screenshots/weekly-performance-pipeline/04-swagger-week-not-computed-a.png) | El log del mismo `GET` con `week_start=2026-10-19`: 404 |
| [Semana no calculada: respuesta](../screenshots/weekly-performance-pipeline/04-swagger-week-not-computed-b.png) | El 404 «Esa semana no la ha calculado ninguna ejecución correcta del pipeline.» No se confunde «sin calcular» con «sin actividad» |
| [Línea de comandos, `--dry-run`](../screenshots/weekly-performance-pipeline/05-cli-dry-run.png) | `python -m app.reporting --dry-run` contra Supabase. Muestra `source_health` (eventos y sesiones por día, a cero, y los 14 días en silencio) y `capture_coverage`: en la semana del 26-oct, Los Ángeles tiene 4 entradas y 2 despachos, y Zaragoza 3 entradas, todo sin eventos. No escribe nada |

## 7. Limitaciones y pendientes

- **Programación automática** del lunes: aplazada hasta que el backend se despliegue con las imágenes nuevas (§3.3).
  Hasta entonces, «fresco el lunes» depende de lanzarlo a mano.
- Dos KPIs sin datos hasta que negocio defina mínimos por cliente y un proceso de conteo.
- Vista del reporte en el backoffice para Thomas y Ana: fuera del alcance del BRIEFING; es el siguiente paso natural.
- La tabla del reporte no distingue entorno: cada entorno debe usar su propia base.
- Ejecución síncrona y una a la vez: suficiente para el volumen actual (milisegundos con decenas de eventos); con
  mucho más volumen, el mismo flow pasaría a una cola.
- **Alertas por email (decidido, sin implementar):** cuando una corrida falle o tenga avisos, un email al
  desarrollador con el servicio de email que ya usa la API (Resend). El remitente tiene que ser del dominio verificado
  `rubenlosada.com` (Resend no puede enviar desde una dirección de Gmail); el destinatario, una variable de entorno
  nueva del `.env`. Hasta entonces los avisos quedan en el registro y en el log.
- `capture_gap` en Supabase: hay órdenes sin evento (semana del 26-oct, anterior a la captura, y una entrada de Los
  Ángeles en la semana del 9-nov). Conviene revisar si esa orden se creó sin `TELEMETRY_PSEUDONYM_KEY` (los eventos
  de órdenes la exigen).
