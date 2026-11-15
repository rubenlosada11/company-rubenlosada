# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## Incident analyzer

CLI for the CX incidents CSV analyzer ([`CONTEXT-incidencias.es.md`](../CONTEXT-incidencias.es.md)). Validation,
metrics and export live in [`packages/analisis-incidencias`](../packages/analisis-incidencias/README.md), imported from
`src/` without installing it. Requires Python ≥ 3.11 (standard library only). Output is in Spanish.

- [`analyze.py`](./analyze.py): `python analyze.py incidents-trackflow.csv [-o results.csv]` (run from `scripts/`).
- [`incidents-trackflow.csv`](./incidents-trackflow.csv): exercise test file (100 rows, fictitious data).
- Tests (from the repo root): `python -m pytest scripts/tests packages/analisis-incidencias/tests`.

Full details in the Spanish version: [README.es.md](./README.es.md) and in
[`docs/analizador-incidencias.md`](../docs/analizador-incidencias.md).

## Incident manager seed

[`seed_incidents.py`](./seed_incidents.py) loads the historical CSV into the incident manager database of
`services/api`, applying the mappings in [`CONTEXT-gestor-incidencias.es.md`](../CONTEXT-gestor-incidencias.es.md). It is
idempotent and needs the API environment. From the repo root, with the API stopped:
`uv run --project services/api python scripts/seed_incidents.py`. Details in the Spanish version and in
[`docs/gestor-incidencias.md`](../docs/gestor-incidencias.md).

## Nightly telemetry export

[`nightly_export.py`](./nightly_export.py) (ticket DEV-53) is a process **independent of the API**, meant for a 02:00
UTC `cron` job: it exports the previous UTC day's `telemetry_events` (or `TARGET_DATE=YYYY-MM-DD`) to
`data/raw/telemetry_YYYY-MM-DD.csv` (audit copy, git-ignored), runs the Milestone 6 pipeline in a subprocess and records
each run in the `job_runs` table (per-date idempotency and an atomic PostgreSQL lock). From the repo root:
`uv run --project services/api --env-file services/api/.env python scripts/nightly_export.py`. Details in the Spanish
version and in [`docs/telemetry/nightly-export.md`](../docs/telemetry/nightly-export.md).
