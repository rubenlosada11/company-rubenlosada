-- Migración 20261113120000 — Pipeline de desempeño semanal: esquema `reporting` (PostgreSQL / Supabase).
--
-- Diseño: docs/reporting/PIPELINE_DESIGN.md. Se aplica una vez sobre la base de `DATABASE_URL`, desde el SQL Editor de
-- Supabase o con psql, **después** de la migración de telemetría (20261110120000):
--
--     psql "<cadena de conexión de Supabase>" -v ON_ERROR_STOP=1 -f migrations/20261113120000_reporting_weekly_performance.sql
--
-- Es idempotente (IF NOT EXISTS): repetirla no cambia nada ni borra datos. No contiene credenciales. No toca
-- `public.telemetry_events`: el pipeline solo la lee.
-- En SQLite (desarrollo local y tests) la API crea tablas equivalentes sin esta migración (`app/reporting/tables.py`).

begin;

-- 1. Esquema dedicado: los resultados del pipeline nunca se mezclan con la telemetría cruda.
create schema if not exists reporting;
comment on schema reporting is 'Tablas calculadas por los pipelines de reporte de TrackFlow (solo las escribe la API).';

-- 2. Tabla de destino. Columnas exactas del BRIEFING (CONTEXT-datapipelines.es.md §5); las restricciones `check`
--    con nombre se añaden sin cambiar el contrato. El `unique` es la base de la idempotencia (upsert).
create table if not exists reporting.weekly_warehouse_client_performance (
    id                       uuid        primary key default gen_random_uuid(),
    warehouse                text        not null,
    client_id                text        not null,
    week_start               date        not null,
    inbound_units_count      integer     not null default 0,
    outbound_orders_count    integer     not null default 0,
    stockout_events_count    integer     not null default 0,
    discrepancy_events_count integer     not null default 0,
    discrepancy_rate         numeric     not null default 0,
    computed_at              timestamptz not null default now(),
    unique (warehouse, client_id, week_start),
    constraint wwcp_warehouse_check check (warehouse in ('los_angeles', 'zaragoza')),
    constraint wwcp_week_start_monday_check check (extract(isodow from week_start) = 1),
    constraint wwcp_counts_check check (
        inbound_units_count >= 0 and outbound_orders_count >= 0
        and stockout_events_count >= 0 and discrepancy_events_count >= 0
    ),
    constraint wwcp_discrepancy_rate_check check (discrepancy_rate >= 0)
);

comment on table reporting.weekly_warehouse_client_performance is
    'Reporte Semanal de Desempeño por Almacén y Cliente: una fila por almacén, cliente y semana ISO (UTC).';
comment on column reporting.weekly_warehouse_client_performance.week_start is 'Lunes de la semana ISO (UTC).';
comment on column reporting.weekly_warehouse_client_performance.inbound_units_count is
    'Volumen de entrada: suma de quantity de inbound_order_created.';
comment on column reporting.weekly_warehouse_client_performance.outbound_orders_count is
    'Throughput de salida: número de outbound_order_created.';
comment on column reporting.weekly_warehouse_client_performance.stockout_events_count is
    'Frecuencia de quiebre de stock: número de stock_threshold_triggered.';
comment on column reporting.weekly_warehouse_client_performance.discrepancy_events_count is
    'Número de inventory_discrepancy_detected (apoyo de la tasa).';
comment on column reporting.weekly_warehouse_client_performance.discrepancy_rate is
    'discrepancy_events_count / outbound_orders_count (0 si no hubo pedidos); puede superar 1.';
comment on column reporting.weekly_warehouse_client_performance.computed_at is 'Último recálculo de la fila.';

-- La consulta habitual es «todas las filas de una semana»: el índice único empieza por warehouse, no sirve.
create index if not exists wwcp_week_start_idx
    on reporting.weekly_warehouse_client_performance using btree (week_start);

-- 3. Registro de ejecuciones (genérico: columna `pipeline`). Auditoría de cada ejecución, también de las fallidas.
create table if not exists reporting.pipeline_runs (
    id              uuid        primary key default gen_random_uuid(),
    pipeline        text        not null,
    status          text        not null check (status in ('running', 'succeeded', 'failed')),
    trigger         text        not null check (trigger in ('api', 'cli')),
    triggered_by    text,
    environment     text        not null,
    week_from       date        not null,
    week_to         date        not null,
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,
    duration_ms     integer     check (duration_ms >= 0),
    events_read     integer     check (events_read >= 0),
    events_rejected integer     check (events_rejected >= 0),
    rows_upserted   integer     check (rows_upserted >= 0),
    rows_deleted    integer     check (rows_deleted >= 0),
    stats           jsonb,
    error           text,
    check (week_from <= week_to)
);

comment on table reporting.pipeline_runs is 'Ejecuciones de los pipelines de reporte: parámetros, estado y resultado.';
comment on column reporting.pipeline_runs.triggered_by is 'Id interno del usuario (trigger = api); nunca su email.';
comment on column reporting.pipeline_runs.stats is 'Eventos leídos por event_type y rechazos por event_type y motivo.';

create index if not exists pipeline_runs_pipeline_started_idx
    on reporting.pipeline_runs using btree (pipeline, started_at desc);

-- 4. Acceso. La API escribe con su propio rol de `DATABASE_URL` (propietario). La API REST de Supabase
--    (anon/authenticated) no ve nada: RLS activado sin políticas y sin privilegios. `service_role` solo lee.
alter table reporting.weekly_warehouse_client_performance enable row level security;
alter table reporting.pipeline_runs enable row level security;

revoke all on schema reporting from public, anon, authenticated;
revoke all on all tables in schema reporting from public, anon, authenticated, service_role;
grant usage on schema reporting to service_role;
grant select on reporting.weekly_warehouse_client_performance, reporting.pipeline_runs to service_role;

commit;
