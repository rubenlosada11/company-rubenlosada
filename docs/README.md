# `docs` folder

This folder holds **cross-cutting documentation** for the monorepo: architecture guides, technical decisions, conventions, processes, and any material shared across applications, pipelines, agents, and workflows.

- **Main purpose**: provide a single place for “global” project documentation (not tied to one app or agent only).
- **Recommendation**: organize docs by topic (architecture, deployment, data, security, observability, etc.) and keep links from each component’s README to these guides.

> _Spanish version: [README.es.md](./README.es.md)._

## Existing documents

- [`hitos.md`](./hitos.md) — record of completed milestones, their folders, and their public demos (in Spanish).
- [`ARCHITECTURE_PROPOSAL.md`](./ARCHITECTURE_PROPOSAL.md) — backend architecture proposal (FastAPI modular monolith
  by business domain) for `services/api/`; not implemented yet (in Spanish).
- [`analizador-incidencias.md`](./analizador-incidencias.md) — CX incidents CSV analyzer: script, API, backoffice page,
  validation rules, metrics and decisions (in Spanish).
- [`pruebas-analizador-incidencias.md`](./pruebas-analizador-incidencias.md) — analyzer test record (in Spanish).
- [`gestor-incidencias.md`](./gestor-incidencias.md) — centralized incident manager: model, historical CSV seed,
  endpoints, backoffice pages, error handling, tests and limitations (in Spanish).
- [`inventario.md`](./inventario.md) — Milestone 5, inventory backend: `/inventory` API with SQLModel, mapping to the
  briefing's file structure, per-warehouse stock rules, seed data, Supabase and limitations (in Spanish).
- [`telemetry/telemetry-plan.md`](./telemetry/telemetry-plan.md) and
  [`telemetry/event-schemas.json`](./telemetry/event-schemas.json) — telemetry plan (design, in Spanish): 43 events,
  envelope, allowlists, privacy and retention (validatable JSON Schema).
- [`telemetry/telemetry-capture.md`](./telemetry/telemetry-capture.md) — telemetry capture (in Spanish): backoffice
  `TelemetryService` (`track()`, batching, retries, `sendBeacon`), temporary receiver `POST /telemetry/events`,
  instrumented events, variables, tests and limitations.
- [`telemetry/telemetry-storage.md`](./telemetry/telemetry-storage.md) — telemetry storage (in Spanish):
  `telemetry_events` table in Supabase (migration, indexes, RLS and immutability), per-event validation with partial
  batch acceptance, bulk insert and the `{received, stored, rejected}` response.
- [`docker.md`](./docker.md) — Docker setup of the monorepo (in Spanish): `interfaces` (website + backoffice) and
  `backend` (API) containers, development Compose with hot reload, production Compose, environment variables and
  deployment to the VPS without public access.
- [`despliegue-api.md`](./despliegue-api.md) — deployment instructions (not executed) for `services/api` and the
  production backoffice: tarball, `uv`, variables, proxy, authentication and checks (in Spanish).
