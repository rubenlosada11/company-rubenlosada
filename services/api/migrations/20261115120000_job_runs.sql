-- Migración 20261115120000 — Procesos en segundo plano (DEV-53): tabla `job_runs` (PostgreSQL / Supabase).
--
-- Documentación: docs/telemetry/nightly-export.md. Se aplica una vez sobre la base de `DATABASE_URL`, desde el SQL
-- Editor de Supabase o con psql, **después** de la migración de telemetría (20261110120000):
--
--     psql "<cadena de conexión de Supabase>" -v ON_ERROR_STOP=1 -f migrations/20261115120000_job_runs.sql
--
-- Es idempotente (IF NOT EXISTS): repetirla no cambia nada ni borra datos. No contiene
-- credenciales. No toca `public.telemetry_events` ni `reporting.pipeline_runs`.
-- En SQLite (desarrollo local y tests) la API crea una tabla equivalente sin esta migración (`app/jobs/job_runner.py`).
--
-- `job_runs` registra la ORQUESTACIÓN de los procesos en segundo plano (p. ej. `nightly_export`: exportación CSV +
-- lanzamiento del pipeline en un subprocess). Lo que pasa DENTRO del pipeline ETL (fases, filas, semanas) sigue en
-- `reporting.pipeline_runs`: las dos tablas no se mezclan.

begin;

-- 1. Tabla. Una fila por intento de ejecución: un reintento de la misma fecha es una fila nueva (no hay `unique` sobre
--    `(job_name, target_date)`), así el historial conserva también los intentos fallidos.
create table if not exists public.job_runs (
    id            uuid        primary key default gen_random_uuid(),
    job_name      text        not null,
    target_date   date        not null,
    status        text        not null default 'pending',
    started_at    timestamptz,
    finished_at   timestamptz,
    error_message text,
    created_at    timestamptz not null default now(),
    constraint job_runs_job_name_check check (job_name ~ '^[a-z][a-z0-9_]{0,62}$'),
    -- Máquina de estados: pending → processing → completed | failed (y pending → failed si falla o se abandona antes
    -- de empezar). Las transiciones las valida el job runner con un UPDATE condicionado al estado de origen.
    constraint job_runs_status_check check (status in ('pending', 'processing', 'completed', 'failed')),
    -- Coherencia entre estado y tiempos: `pending` aún no ha empezado; `processing` y `completed` sí; `failed` puede
    -- no haber empezado (fallo o abandono antes de `processing`).
    constraint job_runs_started_check check (
        case status
            when 'pending' then started_at is null
            when 'failed' then true
            else started_at is not null
        end
    ),
    -- Solo los estados finales tienen `finished_at`.
    constraint job_runs_finished_check check ((status in ('completed', 'failed')) = (finished_at is not null)),
    constraint job_runs_error_check check (status = 'failed' or error_message is null),
    constraint job_runs_times_check check (finished_at is null or started_at is null or finished_at >= started_at)
);

comment on table public.job_runs is
    'Ejecuciones de los procesos en segundo plano (job runner): estado global, tiempos y error. El detalle del pipeline ETL está en reporting.pipeline_runs.';
comment on column public.job_runs.job_name is 'Nombre del proceso (p. ej. nightly_export).';
comment on column public.job_runs.target_date is 'Día (UTC) de los datos que procesa la ejecución.';
comment on column public.job_runs.status is 'pending, processing (candado activo), completed o failed.';
comment on column public.job_runs.started_at is 'Paso a processing: inicio real del trabajo.';
comment on column public.job_runs.finished_at is 'Paso a completed o failed.';
comment on column public.job_runs.error_message is 'Tipo y resumen del error (sin credenciales ni datos de telemetría).';
comment on column public.job_runs.created_at is 'Creación del registro (pending).';

-- 2. Índices.
-- Consulta de idempotencia («¿hay una ejecución completed de este job para este día?») e historial por fecha. Es un
-- índice de CONSULTA, no único: los reintentos legítimos de una fecha deben poder registrarse.
create index if not exists job_runs_job_name_target_date_idx
    on public.job_runs using btree (job_name, target_date);

-- Candado: como mucho UNA ejecución activa (pending o processing) por job. El INSERT del registro `pending` es la
-- adquisición: si dos procesos lo intentan a la vez, PostgreSQL deja pasar uno y el otro recibe una violación de
-- unicidad (23505) sin crear ninguna fila. Al pasar a completed o failed la fila sale del índice y el candado queda
-- libre. Es atómico porque lo garantiza el propio índice, no una consulta previa.
create unique index if not exists job_runs_one_active_idx
    on public.job_runs using btree (job_name) where status in ('pending', 'processing');

-- 3. Acceso. El job runner escribe con el rol de `DATABASE_URL` (propietario). La API REST de Supabase
--    (anon/authenticated) no ve nada: RLS activado sin políticas y sin privilegios. `service_role` solo lee.
alter table public.job_runs enable row level security;
revoke all on table public.job_runs from public, anon, authenticated, service_role;
grant select on table public.job_runs to service_role;

commit;
