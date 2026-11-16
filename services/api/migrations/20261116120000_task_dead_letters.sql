-- Migración 20261116120000 — Colas de mensajes y tareas asíncronas (DEV-55): tabla `task_dead_letters` (PostgreSQL /
-- Supabase), la Dead Letter Queue persistente de Celery.
--
-- Documentación: docs/async-tasks.md. Se aplica una vez sobre la base de `DATABASE_URL`, desde el SQL Editor de
-- Supabase o con psql:
--
--     psql "<cadena de conexión de Supabase>" -v ON_ERROR_STOP=1 -f migrations/20261116120000_task_dead_letters.sql
--
-- Es idempotente (IF NOT EXISTS): repetirla no cambia nada ni borra datos. No contiene credenciales. No toca ninguna
-- otra tabla. En SQLite (desarrollo local y tests) la API crea una tabla equivalente sin esta migración
-- (`app/tasks/dead_letters.py`).
--
-- Una fila por tarea que ha fallado DEFINITIVAMENTE (Celery ya no la va a volver a ejecutar): reintentos agotados,
-- error permanente, tiempo máximo superado o mensaje caducado. Los reintentos intermedios no se guardan aquí (están en
-- los logs del worker y en Flower). El estado en vivo de las tareas está en Redis (result backend), que caduca a las
-- 24 h; esta tabla es el registro duradero.

begin;

-- 1. Tabla.
create table if not exists public.task_dead_letters (
    id             uuid        primary key default gen_random_uuid(),
    task_id        text        not null,
    task_name      text        not null,
    reason         text        not null,
    attempts       integer,
    max_retries    integer,
    exception_type text        not null,
    error_message  text        not null,
    task_kwargs    jsonb,
    worker         text,
    failed_at      timestamptz not null,
    created_at     timestamptz not null default now(),
    -- Idempotencia: un mismo fallo notificado dos veces (p. ej. el worker cae tras escribir aquí y antes de confirmar
    -- el mensaje, y Celery lo vuelve a entregar) solo se guarda una vez: `INSERT … ON CONFLICT (task_id) DO NOTHING`.
    constraint task_dead_letters_task_id_key unique (task_id),
    constraint task_dead_letters_reason_check
        check (reason in ('retries_exhausted', 'permanent_error', 'time_limit', 'expired')),
    -- `attempts` es NULL solo cuando el worker no puede saberlo (timeout duro, registrado por el proceso padre).
    constraint task_dead_letters_attempts_check check (attempts is null or attempts >= 1)
);

comment on table public.task_dead_letters is
    'Dead Letter Queue de Celery: tareas que han fallado definitivamente (sin datos de negocio ni credenciales).';
comment on column public.task_dead_letters.task_id is 'Identificador de la tarea de Celery (el que devuelve el 202).';
comment on column public.task_dead_letters.task_name is 'Tarea de Celery, p. ej. reporting.run_weekly_performance.';
comment on column public.task_dead_letters.reason is
    'retries_exhausted (1 intento + 3 reintentos fallidos), permanent_error, time_limit o expired.';
comment on column public.task_dead_letters.attempts is 'Intento en el que falló del todo (1 = inicial; 4 = tras 3 reintentos).';
comment on column public.task_dead_letters.exception_type is 'Tipo de la causa raíz del error.';
comment on column public.task_dead_letters.error_message is 'Cadena completa de errores, con credenciales censuradas.';
comment on column public.task_dead_letters.task_kwargs is 'Argumentos escalares de la tarea (identificadores y parámetros).';
comment on column public.task_dead_letters.worker is 'Worker que ejecutó el último intento.';
comment on column public.task_dead_letters.failed_at is 'Momento del fallo definitivo (UTC).';

-- 2. Índices. Consulta habitual: los últimos fallos (GET /tasks/dead-letters).
create index if not exists task_dead_letters_failed_at_idx
    on public.task_dead_letters using btree (failed_at);

-- 3. Acceso. El worker escribe y la API lee con el rol de `DATABASE_URL` (propietario). La API REST de Supabase
--    (anon/authenticated) no ve nada: RLS activado sin políticas y sin privilegios. `service_role` solo lee.
alter table public.task_dead_letters enable row level security;
revoke all on table public.task_dead_letters from public, anon, authenticated, service_role;
grant select on table public.task_dead_letters to service_role;

commit;
