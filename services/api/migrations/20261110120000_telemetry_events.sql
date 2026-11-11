-- Migración 20261110120000 — Almacenamiento de telemetría: tabla `telemetry_events` (PostgreSQL / Supabase).
--
-- Documentación: docs/telemetry/telemetry-storage.md. Se aplica una vez sobre la base de `DATABASE_URL`, desde el
-- SQL Editor de Supabase o con psql:
--
--     psql "<cadena de conexión de Supabase>" -v ON_ERROR_STOP=1 -f migrations/20261110120000_telemetry_events.sql
--
-- Es idempotente (IF NOT EXISTS / OR REPLACE): repetirla no cambia nada ni borra datos. No contiene credenciales.
-- En SQLite (desarrollo local y tests) la API crea una tabla equivalente sin esta migración (`app/telemetry/storage.py`).

begin;

-- 1. Tabla. Una fila por evento validado con `TelemetryEvent`: los 10 campos del envelope (§8.1 del plan), con
--    `eventId` como clave primaria (deduplicación) y `properties` en `tags` (solo las claves de la allowlist).
create table if not exists public.telemetry_events (
    id             uuid        primary key,
    event_type     text        not null,
    "timestamp"    timestamptz not null,
    service        text        not null check (service in ('frontend', 'backend', 'internal_process')),
    tags           jsonb       not null check (jsonb_typeof(tags) = 'object'),
    session_id     uuid,
    user_id        text,
    request_id     uuid,
    schema_version text        not null,
    environment    text        not null check (environment in ('development', 'test', 'production'))
);

comment on table public.telemetry_events is
    'Eventos de telemetría de TrackFlow (solo inserción). Contrato: docs/telemetry/event-schemas.json.';
comment on column public.telemetry_events.id is 'eventId del envelope (UUID v4, o v5 determinista).';
comment on column public.telemetry_events."timestamp" is 'Momento del hecho (UTC), no el de recepción.';
comment on column public.telemetry_events.service is 'source del envelope: frontend, backend o internal_process.';
comment on column public.telemetry_events.tags is 'properties del envelope, limitadas a la allowlist del event_type.';
comment on column public.telemetry_events.user_id is 'Seudónimo usr_… (HMAC); nunca el id real del usuario.';

-- 2. Índices: rangos de fechas, filtro por tipo de evento y consultas sobre `tags` (@>, ?, ?|, ?&).
--    La clave primaria ya indexa `id`: no se añade ningún otro índice.
create index if not exists telemetry_events_timestamp_idx on public.telemetry_events using btree ("timestamp");
create index if not exists telemetry_events_event_type_idx on public.telemetry_events using btree (event_type);
create index if not exists telemetry_events_tags_idx on public.telemetry_events using gin (tags);

-- 3. Acceso. La API escribe con su propio rol de `DATABASE_URL`; la API REST de Supabase (anon/authenticated) no
--    ve ni escribe nada: RLS activado sin políticas y sin privilegios (los privilegios por defecto del esquema
--    `public` se los daban todos). `service_role` solo puede leer e insertar.
alter table public.telemetry_events enable row level security;
revoke all on table public.telemetry_events from public, anon, authenticated, service_role;
grant select, insert on table public.telemetry_events to service_role;

-- 4. Inmutabilidad en la base (no solo en la API): UPDATE, DELETE y TRUNCATE fallan para cualquier rol, incluido el
--    propietario. La purga de retención (§16 del plan) tendrá que hacerse con una migración propia y explícita.
create or replace function public.telemetry_events_reject_changes()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    raise exception 'telemetry_events es de solo inserción: % no está permitido', tg_op
        using errcode = 'insufficient_privilege';
end;
$$;

revoke all on function public.telemetry_events_reject_changes() from public, anon, authenticated;

drop trigger if exists telemetry_events_no_update_delete on public.telemetry_events;
create trigger telemetry_events_no_update_delete
    before update or delete on public.telemetry_events
    for each row execute function public.telemetry_events_reject_changes();

drop trigger if exists telemetry_events_no_truncate on public.telemetry_events;
create trigger telemetry_events_no_truncate
    before truncate on public.telemetry_events
    for each statement execute function public.telemetry_events_reject_changes();

commit;
