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
