# Pipeline de desempeño semanal — Implementación, operación y verificación

> Reporte Semanal de Desempeño por Almacén y Cliente (práctica sin número de hito). El diseño, escrito antes del
> código, está en [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md); este documento cuenta cómo quedó, cómo se ejecuta y
> cómo se ha comprobado. BRIEFING: [`CONTEXT-datapipelines.es.md`](../../CONTEXT-datapipelines.es.md).

## 1. Qué hay y dónde

| Pieza | Fichero |
| --- | --- |
| Migración del esquema `reporting` (tabla del reporte + registro de ejecuciones) | [`services/api/migrations/20261113120000_reporting_weekly_performance.sql`](../../services/api/migrations/20261113120000_reporting_weekly_performance.sql) |
| Semanas ISO en UTC y ventana | [`app/reporting/weeks.py`](../../services/api/app/reporting/weeks.py) |
| Subflow 1 · extract (`telemetry_events`, `READ ONLY`) | [`app/reporting/extract.py`](../../services/api/app/reporting/extract.py) |
| Subflow 2 · validate (reglas de calidad) | [`app/reporting/validate.py`](../../services/api/app/reporting/validate.py) |
| Subflow 3 · aggregate (Pandas) | [`app/reporting/aggregate.py`](../../services/api/app/reporting/aggregate.py) |
| Subflow observe (salud del origen y cobertura frente al inventario) | [`app/reporting/observe.py`](../../services/api/app/reporting/observe.py) |
| Subflow 4 · load (upsert + reconciliación, `run_id`, cambios por semana) | [`app/reporting/load.py`](../../services/api/app/reporting/load.py) |
| Registro de ejecuciones | [`app/reporting/runs.py`](../../services/api/app/reporting/runs.py) |
| Flow (`run_weekly_performance`) | [`app/reporting/flow.py`](../../services/api/app/reporting/flow.py) |
| Línea de comandos (`python -m app.reporting`) | [`app/reporting/__main__.py`](../../services/api/app/reporting/__main__.py) |
| Endpoints `/reporting` | [`app/routes/reporting.py`](../../services/api/app/routes/reporting.py) |
| Tests | [`services/api/tests/reporting/`](../../services/api/tests/reporting/) |

`services/reporting/` del BRIEFING = `services/api/app/reporting/` en este repo (misma API que la telemetría; ver
PIPELINE_DESIGN §5). No se ha tocado `app/telemetry/analysis.py` ni `GET /telemetry/report`, y no se ha añadido
ninguna dependencia (Pandas ya estaba).

## 2. Cómo funciona una ejecución

```text
POST /reporting/pipeline-runs   ─┐
python -m app.reporting (cron)  ─┴─► run_weekly_performance
    1. resolve_window: semanas completas (por defecto, las 2 últimas)       → 422 / código 2 si no es válida
    2. start_run: fila `running` en reporting.pipeline_runs (+ marca las abandonadas)
                  → 409 si ya hay otra `running` (índice único parcial: también entre cron y API)
    3. extract   SELECT 4 event_type, environment, [inicio, fin)  (READ ONLY)            phase = extracted
    4. validate  rechaza y cuenta por event_type y motivo                                 phase = validated
    5. aggregate (warehouse, client_id, week_start) → 4 KPIs + tasa                       phase = aggregated
    6. observe   eventos/sesiones por día y órdenes del inventario vs. eventos (avisos; nunca falla)
    7. load      DELETE de combinaciones desaparecidas + INSERT … ON CONFLICT DO UPDATE, con run_id (una transacción)
    8. finish_run: `succeeded`, phase = loaded, recuentos y stats  |  `failed` con el tipo de error y la última fase
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

### 3.2. Comandos (Windows PowerShell 5.1, desde `services\api`)

```powershell
cd services\api
uv run --env-file .env python -m app.reporting
uv run --env-file .env python -m app.reporting --week-start 2026-11-02 --weeks 4
uv run --env-file .env python -m app.reporting --dry-run
```

- Sin parámetros: las 2 últimas semanas completas. `--week-start` es la semana más reciente (un lunes ya terminado);
  `--weeks`, cuántas hacia atrás (1–53).
- `--dry-run` hace extract → validate → aggregate y muestra las filas en JSON **sin escribir nada** ni registrar la
  ejecución: sirve para revisar datos reales antes de cargarlos.
- Códigos de salida: 0 bien, 1 la ejecución falló, 2 parámetros no válidos o ejecución ya en curso.
- Entorno de los eventos: `TELEMETRY_ENVIRONMENT` (por defecto `development`).

### 3.3. Programación semanal (aplazada: no forma parte de la entrega)

Lunes a las 06:00 UTC, en el `crontab` del VPS, con el contenedor de la API levantado:

```text
0 6 * * 1  cd /opt/company-rubenlosada && docker compose -f docker-compose.prod.yml exec -T backend python -m app.reporting
```

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
