# Proceso nocturno de telemetría (DEV-53)

> Práctica **Procesos en segundo plano** (AI Engineering, 4Geeks), sin número de hito. Ticket DEV-53: script nocturno
> que exporta la telemetría del día a CSV, lanza el pipeline del Hito 6 y registra sus ejecuciones con una máquina de
> estados persistente, **fuera** del proceso de FastAPI.

| Pieza | Fichero |
| --- | --- |
| Script (orquestación, CSV, subprocess, logs) | [`scripts/nightly_export.py`](../../scripts/nightly_export.py) |
| Job runner (persistencia y estados de `job_runs`) | [`services/api/app/jobs/job_runner.py`](../../services/api/app/jobs/job_runner.py) |
| Migración de `job_runs` | [`services/api/migrations/20261115120000_job_runs.sql`](../../services/api/migrations/20261115120000_job_runs.sql) |
| Tests | [`services/api/tests/jobs/`](../../services/api/tests/jobs/) |
| Pipeline que se lanza (sin cambios) | [`data/pipelines/pipeline.py`](../../data/pipelines/pipeline.py) |

## 1. Arquitectura

Tres componentes con responsabilidades separadas, que solo comparten la base de datos:

```mermaid
flowchart LR
    cron["cron del sistema<br/>0 2 * * * (UTC)"] -->|lanza| job
    subgraph job["scripts/nightly_export.py (proceso independiente)"]
        runner["job runner<br/>app/jobs/job_runner.py"]
        export["exportación CSV"]
    end
    job -->|subprocess.run| pipe["data/pipelines/pipeline.py<br/>(Prefect 3, Hito 6)"]
    runner <-->|estados y candado| jr[("public.job_runs")]
    export -->|SELECT READ ONLY| te[("public.telemetry_events")]
    export --> csv["data/raw/telemetry_YYYY-MM-DD.csv<br/>(copia de auditoría)"]
    pipe -->|SELECT READ ONLY| te
    pipe --> pr[("reporting.pipeline_runs<br/>reporting.weekly_…")]
    api["FastAPI (services/api)"] -->|INSERT eventos| te
```

| Componente | Hace | No hace |
| --- | --- | --- |
| **FastAPI** | Atiende HTTP y guarda la telemetría. | No importa ni arranca el job (lo comprueba un test: `app.main` no carga `app.jobs`). |
| **Job runner + script** | Fecha objetivo, idempotencia, candado, estados de `job_runs`, CSV, lanzar el pipeline, logs. | No calcula KPIs ni conoce las fases del pipeline. |
| **Pipeline ETL** | Sus fases, su registro `pipeline_runs`, lee `telemetry_events` de PostgreSQL. | No lee el CSV. No sabe que lo lanza un job. |

**Por qué un proceso aparte y no dentro de FastAPI** (APScheduler, `@repeat_every`…): con varios workers o réplicas,
cada uno dispararía el job; un reinicio o despliegue a las 02:00 lo perdería; un fallo o un pico de memoria del
pipeline afectaría a las peticiones HTTP; y el ciclo de vida del job quedaría atado al de la API. Un proceso
lanzado por el programador del sistema arranca, hace su trabajo, deja rastro y termina con un código de salida.

El script reutiliza la conexión de la API (`app.database.get_engine`, misma `DATABASE_URL`, mismo driver psycopg) y
la tabla declarada en `app.telemetry.storage`: no hay un segundo cliente ni otra configuración.

## 2. `job_runs` frente a `pipeline_runs`

| | `public.job_runs` (nueva) | `reporting.pipeline_runs` (Hito 6, sin cambios) |
| --- | --- | --- |
| Registra | La **orquestación**: un intento del job nocturno para una fecha | Una ejecución **interna** del pipeline ETL |
| Clave de negocio | `(job_name, target_date)` | `pipeline` + ventana de semanas |
| Estados | `pending`, `processing`, `completed`, `failed` | `running`, `succeeded`, `failed` |
| Detalle | Tiempos y error global (CSV + subprocess) | Fase, eventos leídos, filas escritas, `stats` |
| La escribe | El script nocturno | El pipeline (lo lance el job, la API o una persona) |

Una ejecución nocturna correcta deja una fila en cada tabla. Si el pipeline falla, `pipeline_runs` dice en qué fase
y `job_runs` dice que la noche falló y por qué (código de salida y causa).

Columnas de `job_runs`: `id` (uuid), `job_name`, `target_date` (date), `status`, `started_at`, `finished_at`,
`error_message`, `created_at` (timestamptz). Restricciones:

- `job_runs_status_check`: solo los 4 estados.
- `job_runs_started_check`, `job_runs_finished_check`, `job_runs_error_check`, `job_runs_times_check`: coherencia
  entre estado y tiempos (`processing`/`completed` tienen `started_at`; los finales, `finished_at`; solo `failed`
  tiene `error_message`; `finished_at >= started_at`).
- `job_runs_job_name_check`: nombres en minúsculas (`nightly_export`).
- Índice de consulta `job_runs_job_name_target_date_idx (job_name, target_date)`, **no único**: los reintentos de
  una fecha son filas nuevas y el historial conserva los intentos fallidos.
- Índice único parcial `job_runs_one_active_idx (job_name) where status in ('pending','processing')`: el candado.
- RLS activado sin políticas; `anon`/`authenticated` sin acceso; `service_role` solo lectura (como el resto de tablas).

## 3. Máquina de estados

```mermaid
stateDiagram-v2
    [*] --> pending: create (adquiere el candado)
    pending --> processing: empieza el trabajo
    processing --> completed: CSV + pipeline correctos
    processing --> failed: excepción
    pending --> failed: falla o se abandona antes de empezar
    completed --> [*]
    failed --> [*]
```

- `pending`: registro creado, trabajo aún no empezado. `processing`: trabajo en curso. `completed`/`failed`: finales.
- Las transiciones son *compare-and-set*: `UPDATE … WHERE id = :id AND status IN (<orígenes válidos>)`. Si el estado
  ya cambió (otra ejecución, una recuperación), no se actualiza nada y se lanza `InvalidTransition`.
- **Arista añadida** `pending → failed`: sin ella, un registro `pending` huérfano (el proceso murió entre crearlo y
  pasarlo a `processing`, o falló ese `UPDATE`) bloquearía el job para siempre. No hay estado `cancelled`.

## 4. Candado (exclusión mutua) sin mecanismos paralelos

El problema: «consultar si hay un `processing` y después insertar» deja una ventana en la que dos procesos ven «no
hay nadie» e insertan los dos (*race condition*). Hace falta que comprobar y ocupar sea **una sola operación atómica**.

La solución usa el propio estado de `job_runs`: el índice único parcial solo admite una fila activa por job. El
`INSERT` del registro `pending` **es** la adquisición:

1. Dos procesos insertan a la vez. PostgreSQL deja pasar al primero; el segundo **espera** a que la transacción del
   primero confirme o deshaga.
2. Si confirma, el segundo recibe `23505 unique_violation` (→ `JobAlreadyRunning`) y no deja ninguna fila. Si deshace,
   el segundo inserta y gana.
3. Al pasar a `completed` o `failed`, la fila sale del índice parcial y el candado queda libre, sin borrar nada.

Sin tabla de locks, Redis, ficheros `.lock` ni *advisory locks*. Es el mismo patrón que ya usa `pipeline_runs`
(`pipeline_runs_one_running_idx`). El candado es **por job**, no por fecha: dos fechas distintas tampoco se solapan,
porque las dos lanzarían el mismo pipeline sobre las mismas tablas.

**Caídas abruptas.** Un `try/except/finally` cubre las excepciones de Python (incluido Ctrl+C, y `SIGTERM`, que el
script convierte en excepción), pero **no** un `SIGKILL`, un `kill -9`, el *OOM killer*, un corte de luz o el reinicio
del servidor: el proceso desaparece sin ejecutar nada más y el registro se queda activo. Para eso,
`recover_abandoned_runs` marca `failed` con `error_message = abandoned: …` las activas de más de **2 horas**
(`STALE_AFTER`) justo antes de adquirir. Dos horas superan con margen la duración máxima legítima (timeout del
pipeline de 30 min + exportación de un día); la contrapartida es que, tras una caída, la siguiente ejecución no
puede empezar hasta pasadas esas dos horas (en la práctica, la noche siguiente o un reintento manual posterior).

## 5. Idempotencia por fecha

Ejecutar el job dos veces para el mismo día produce el mismo resultado que ejecutarlo una vez:

- Antes de adquirir: `has_completed_for_date('nightly_export', fecha)` (usa el índice de consulta). Si hay un
  `completed`, termina con código 0 y evento `skipped_duplicate`, sin crear fila ni tocar el CSV.
- Dentro de la transacción de adquisición, ya con el candado, se comprueba otra vez: si otro proceso completó la
  fecha mientras este esperaba, se deshace el `INSERT` y también se omite. Cierra la carrera «comprobé, el otro
  terminó, adquirí».
- Una fecha `failed` **sí** se reintenta: el siguiente intento es otra fila. Nunca se convierte un fallo en éxito.
- Las piezas son idempotentes por sí mismas: el CSV no se reescribe si existe y el pipeline recalcula semanas con
  *upsert*.

`TARGET_DATE` solo acepta días **ya terminados en UTC**: exportar el día en curso y marcarlo `completed` haría que nunca
se exportara completo, porque la idempotencia lo daría por hecho.

## 6. Exportación CSV

`data/raw/telemetry_YYYY-MM-DD.csv` con los eventos de `[00:00, 24:00)` UTC del día objetivo, todos los entornos.

- Columnas reales de `telemetry_events`, en su orden: `id, event_type, timestamp, service, tags, session_id, user_id,
  request_id, schema_version, environment`. UTF-8, cabecera, fechas ISO 8601 en UTC, `tags` como JSON compacto.
- Consulta en transacción `READ ONLY` y lectura por lotes de 1000 (`yield_per`, cursor de servidor en PostgreSQL): no
  se carga el día entero en memoria.
- Escritura atómica sin sobrescribir: temporal oculto en la misma carpeta → `fsync` → `os.link(temporal, destino)`,
  que falla si el destino existe (`os.replace` lo sustituiría) → se borra el temporal. Si algo falla a mitad, no queda
  un CSV incompleto con el nombre definitivo.
- Si el CSV ya existe (p. ej. reintento tras un fallo del pipeline) no se toca y se registra «ya existía».
- Cero eventos: CSV con solo la cabecera (deja constancia de que el día no tuvo eventos).
- Es una **copia de auditoría y recuperación**: el pipeline no la lee; sigue leyendo `telemetry_events` en PostgreSQL.
  Contiene seudónimos (`user_id`, `session_id`), por eso `data/raw/telemetry_*.csv` está en `.gitignore`.

## 7. El pipeline como proceso hijo

```text
<python del venv> data/pipelines/pipeline.py --week-start <lunes>
```

- `subprocess.run` con una lista de argumentos, **sin `shell=True`** (sin interpretación de comillas ni inyección),
  `cwd` = raíz del repo, `stdin` cerrado y el mismo intérprete (`sys.executable`: el venv de la API, con Prefect).
- `--week-start`: lunes de la última semana ISO completa al final de la fecha objetivo. Con la fecha por defecto
  coincide con la ventana por defecto del pipeline; con `TARGET_DATE` recalcula las semanas de esa fecha.
- Código de salida: `0` correcto (también «parcial»); `1` fallido; `2` parámetros o ejecución ya en curso. Cualquier
  código distinto de 0 → `PipelineError` con la causa (`La ejecución ha fallado: …`) y las últimas 15 líneas de stderr.
- Timeout de **30 minutos**: una ejecución normal tarda ~20 s (medido: 18–19 s, la mayoría arrancando el servidor
  temporal de Prefect); coincide con el `ABANDON_AFTER` de `pipeline_runs`, así la siguiente ejecución del pipeline
  recupera el `running` que deje un hijo matado; y es menor que el `STALE_AFTER` de `job_runs` (2 h).
- **stdout/stderr en ficheros temporales, no en pipes.** Prefect arranca su servidor temporal con `Popen` sin
  redirigir salidas: ese nieto hereda los pipes. Si el pipeline supera el timeout, `subprocess.run` mata al hijo y,
  en Windows, se queda esperando a que se cierren los pipes, que el nieto mantiene abiertos. Medido en este equipo:
  un timeout de 3 s tardó 25 s (lo que vivió el nieto); con el servidor de Prefect no terminaría nunca y el job no
  llegaría a `failed`. Con ficheros, el timeout corta a su hora (test de regresión incluido).
- `PYTHONIOENCODING=utf-8` para el hijo (el pipeline imprime «→»; en Windows, cp1252 fallaría).

## 8. Gestión de errores

```text
try:   processing → CSV → pipeline → completed
except BaseException:  log del tipo de fallo → failed (sin ocultar nada) → raise
```

- Cualquier excepción **después de adquirir** (base, disco, pipeline, timeout, Ctrl+C, `SIGTERM`) deja la ejecución
  en `failed` con `error_message` y se vuelve a lanzar: el proceso termina con código distinto de cero.
- Si marcar `failed` también falla (la base cayó), se registra `status_update_failed` y se relanza **la excepción
  original**, no la secundaria. La ejecución queda activa y la recupera la siguiente pasadas 2 h.
- Si falla el paso a `completed` tras un pipeline correcto, la ejecución acaba en `failed`: la siguiente reintenta
  (el CSV ya existe y el pipeline es idempotente).
- `error_message` y los logs nunca llevan la cadena de conexión: de los errores de base solo se guarda el tipo y el
  SQLSTATE; las URL con contraseña se enmascaran (`postgresql://usuario:***@host`).
- Errores **antes** de adquirir (base inalcanzable): `connection_error`, código 1, ninguna fila (no se puede escribir).

## 9. Variables de entorno, instalación y ejecución manual

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | La de `services/api/.env` (Supabase o PostgreSQL). Sin ella, SQLite local de la API. Ya existe: no se duplica. |
| `TARGET_DATE` | Opcional, `YYYY-MM-DD`: día a procesar. **No va en `.env`** (fijaría la fecha para siempre): se pasa por ejecución. |
| `TELEMETRY_ENVIRONMENT` | La lee el pipeline (entorno de los eventos del reporte). Ya existe. |
| `PREFECT_API_URL` | Opcional: servidor de Prefect dedicado (evita el servidor temporal; ver §12). |

Requisitos: la migración `20261115120000_job_runs.sql` aplicada en la base (SQL Editor de Supabase, después de las de
telemetría y reporting) y el entorno de la API (`uv sync` en `services\api`). Sin dependencias nuevas.

En PowerShell, desde la raíz del repo (un comando por línea):

```powershell
uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py
$env:TARGET_DATE = "2026-11-14"
uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py
Remove-Item Env:TARGET_DATE
```

(O `python scripts/nightly_export.py` con el venv de `services/api` activado y las variables cargadas.)

Códigos de salida: `0` completada u omitida por duplicado · `1` fallida · `2` `TARGET_DATE` no válida · `75` omitida por
candado (`EX_TEMPFAIL`: «vuelve a intentarlo más tarde», distinto de un fallo) · `130` Ctrl+C · `143` `SIGTERM`.

## 10. Programación nocturna (cron)

**Decisión: `crontab` del sistema operativo**, no un contenedor programador. Motivos (infraestructura real del repo):
la imagen Docker del backend solo copia `services/api/` (ni `data/` ni `scripts/`, PIPELINE_DESIGN §18.10), cambiar
imágenes o `docker-compose` requiere confirmación, y el pipeline semanal ya quedó diseñado con el `cron` del host
(`docs/reporting/weekly-performance-pipeline.md` §3.3). Un contenedor programador sería la opción natural cuando la
imagen incluya `data/` y `scripts/`.

Expresión: **`0 2 * * *`** = minuto 0, hora 2, todos los días del mes, todos los meses, todos los días de la semana.
A las 02:00 UTC el día anterior ha terminado hace 2 horas (margen para eventos que llegan tarde: lotes y *beacons* del
navegador) y queda lejos del informe del lunes a las 07:00.

```text
# crontab -e  del usuario que tiene el repositorio (sin sudo)
0 2 * * * cd /opt/company-rubenlosada && $HOME/.local/bin/uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py >> $HOME/logs/trackflow/nightly_export.log 2>&1
```

Comprobaciones antes de instalarla (no se ha instalado: el stack del VPS está parado y no apunta a la base real):

- **Zona horaria**: cron usa la del sistema. `timedatectl` debe mostrar `Etc/UTC` (lo habitual en un VPS); si no, usar
  `CRON_TZ=UTC` donde el cron lo admita (cronie) o un *timer* de systemd con `OnCalendar=*-*-* 02:00:00 UTC`. La fecha
  objetivo no depende de esto: el script siempre calcula en UTC.
- **Directorio de trabajo**: `cd` a la raíz del repo (el script resuelve sus rutas desde su propia ubicación, pero
  `uv --project` y `--env-file` son relativos).
- **Intérprete y entorno**: cron no carga el `PATH` del usuario: ruta absoluta de `uv` (`which uv`) y `uv sync` hecho
  en `services/api`. El pipeline hijo usa el mismo intérprete.
- **Variables**: `services/api/.env` con `DATABASE_URL` (permisos `600`). Nada de secretos en el crontab.
- **Acceso a PostgreSQL**: `uv run … python scripts/nightly_export.py` a mano con `TARGET_DATE` de un día pasado.
- **Logs y permisos**: `mkdir -p $HOME/logs/trackflow`; escritura en `data/raw/` para ese usuario; rotación con
  `logrotate` (`daily`, `rotate 30`, `copytruncate`).
- Un solapamiento con una ejecución manual no rompe nada: la segunda sale con `75`.

En el equipo de desarrollo (Windows) no se programa: se ejecuta a mano (§9).

## 11. Logs

Una línea por evento, en stderr (cron la añade al fichero de log), UTF-8:

```text
<timestamp UTC> <NIVEL> job=nightly_export target_date=<día> run_id=<uuid|-> status=<estado|-|skipped> event=<evento> <mensaje>
```

- `INFO`: `job_started`, `lock_acquired`, `processing`, `export_started`, `export_completed`, `pipeline_started`,
  `pipeline_completed` (+ `pipeline_stdout`), `skipped_duplicate`, `skipped_locked`, `job_completed`.
- `ERROR`: `connection_error`, `export_failed`, `pipeline_failed` / `pipeline_timeout` (+ `pipeline_stderr`, últimas 15
  líneas), `status_update_failed`, `interrupted`, `unexpected_error` (con traza), `job_failed`, `invalid_target_date`.
- `status=skipped` no es un estado de `job_runs`: una ejecución omitida no crea fila.
- Sin secretos ni datos de telemetría: solo recuentos, nombres de fichero, ids de ejecución y causas.

Ejemplo real (PostgreSQL local, `TARGET_DATE=2026-11-13`, tres instancias lanzadas a la vez):

```text
2026-11-15T21:00:01.150Z INFO job=nightly_export target_date=2026-11-13 run_id=5dd38d15-… status=pending event=lock_acquired registro pending creado: candado adquirido
2026-11-15T21:00:01.153Z INFO job=nightly_export target_date=2026-11-13 run_id=- status=skipped event=skipped_locked otra ejecución tiene el candado (run_id=5dd38d15-…, status=pending, target_date=2026-11-13): se aborta sin ejecutar el pipeline
2026-11-15T21:00:20.412Z INFO job=nightly_export target_date=2026-11-13 run_id=5dd38d15-… status=processing event=pipeline_completed pipeline correcto en 19.2 s: Ejecución c28a50ac-… succeeded: semanas 2026-10-26 → 2026-11-02, 70 eventos leídos (0 rechazados), 4 filas escritas, 0 eliminadas, 5654 ms, caché de la transformación: hit.
2026-11-15T21:00:20.416Z INFO job=nightly_export target_date=2026-11-13 run_id=5dd38d15-… status=completed event=job_completed ejecución completada en 19.6 s
```

## 12. Tests y verificación

```powershell
cd services\api
uv run pytest tests/jobs -q
$env:JOBS_TEST_DATABASE_URL = "postgresql+psycopg://postgres:@127.0.0.1:5432/postgres"
uv run pytest tests/jobs/test_job_runner_postgres.py
```

- `test_job_runner.py` (SQLite): creación, transiciones válidas e inválidas, *compare-and-set*, `CHECK` de la base,
  candado, idempotencia, reintentos, recuperación de abandonadas y errores sin credenciales.
- `test_job_runner_postgres.py` (PostgreSQL local y desechable, solo `localhost`): 12 hilos y **6 procesos
  independientes** compitiendo en el mismo instante (gana uno, los demás no dejan fila), espera ante un candado sin
  confirmar (y adquisición si se deshace), carrera de idempotencia y `CHECK` de la migración.
- `test_nightly_export.py`: fecha UTC (también desde otras zonas horarias), `TARGET_DATE` válida e inválida, corte del
  día en el CSV, cabecera y cero eventos, no sobrescritura, escritura atómica ante un fallo a mitad, subprocess
  (salida, código ≠ 0, timeout, nieto que retiene las salidas), orquestación completa, duplicado, candado, fallos de
  exportación, pipeline, timeout, interrupción y actualización de estado, logs y que FastAPI no importa el job.

Verificación real (2026-11-15) con el script, el pipeline real del Hito 6 en subprocess y PostgreSQL 16 local con las
tres migraciones (130 eventos de inventario de prueba del 2 al 14 de noviembre):

| Prueba | Resultado |
| --- | --- |
| Estructura de la migración (27 comprobaciones: columnas, 6 `CHECK`, índices, RLS, transiciones, rechazos, plan de consulta) | Correcta; segunda aplicación sin cambios |
| `TARGET_DATE=2026-11-14` | `pending → processing → completed`, CSV de 10 eventos (incluido el de las 00:00:00), pipeline en 18 s |
| Misma fecha otra vez | `skipped_duplicate` en 0,25 s; CSV con la misma huella y `mtime`; `pipeline_runs` sin cambios |
| 3 instancias a la vez (`2026-11-13`) | Una `completed`; dos con código 75 sin fila; `pipeline_runs` +1 |
| Base sin el esquema del pipeline | Pipeline con código 1 → `failed` con `La ejecución ha fallado: UndefinedTable (SQLSTATE 42P01)` |
| Reintento tras aplicar el esquema | `completed`; el CSV existente no se reescribe |
| Timeout real de 6 s | `failed` a los 6 s (ver la limitación del servidor de Prefect en §13) |
| Base inalcanzable con contraseña en la URL | `connection_error`, código 1, la contraseña no aparece, sin CSV |
| `TARGET_DATE` `2026-02-30`, `15/11/2026`, hoy | Código 2 con mensaje claro, sin tocar la base |
| API (`uvicorn`) | `/health` 200; `POST /telemetry/events` guarda (130 → 131); `job_runs` intacta |
| **Supabase** (migración aplicada el 2026-11-15; misma verificación de estructura) | Por defecto (día 14, sin eventos): `completed`, CSV con solo la cabecera · 2 instancias a la vez con `TARGET_DATE=2026-11-11`: una `completed` (47 eventos, pipeline en 18 s) y otra `skipped_locked` (código 75) · repetición del 11: `skipped_duplicate` |
| Regresiones | Suite de la API: 1805 tests (con los de PostgreSQL); `tests/pipelines` 15; scripts + analisis-incidencias 196 |

## 13. Limitaciones y recuperación

- **Caída abrupta** (`SIGKILL`, OOM, reinicio): ningún código de limpieza se ejecuta. La ejecución queda activa hasta
  que otra la marca `abandoned` pasadas 2 h. Recuperación manual inmediata, si se sabe que el proceso no vive:
  `update job_runs set status = 'failed', finished_at = now(), error_message = 'abandoned: manual' where job_name =
  'nightly_export' and status in ('pending', 'processing');` y relanzar con `TARGET_DATE`.
- **Servidor temporal de Prefect huérfano tras un timeout**: `subprocess.run` solo mata al hijo directo; el servidor
  temporal que arrancó el pipeline (y su hijo) siguen vivos escuchando en `127.0.0.1:8000-8999` (comprobado en la
  prueba de timeout real). Hay que pararlos a mano (`pkill -f prefect.server.api.server`). Mitigación recomendada:
  un servidor de Prefect dedicado (`PREFECT_API_URL`), que además quita los ~2 s por subflow del servidor temporal.
- Windows no entrega `SIGTERM` (lo mata sin aviso): ahí solo Ctrl+C pasa por `failed`.
- Una ejecución viva de más de 2 h se trataría como abandonada y otra podría empezar; la vieja, al terminar, no podría
  cerrar su registro (`InvalidTransition`, código 1). Imposible con los timeouts actuales salvo una exportación colgada.
- La exportación no tiene timeout propio (solo el `connect_timeout` de 10 s de la conexión).
- Sin alertas: un fallo queda en `job_runs`, en el log y en el código de salida. La alerta por email sigue pendiente
  (como en el pipeline semanal).
- El cron está documentado pero **no instalado**.
