# `packages` folder

This folder contains **shared packages** for the monorepo: internal libraries, utilities, types, shared components, SDKs, clients, and any code reused by multiple applications, agents, or pipelines.

Each subfolder under `packages/` should represent **one versionable package** (for example `shared-types`, `ui`, `analytics-sdk`) with its own README.

- **Main purpose**: encourage reuse and consistency across all company deliverables.
- **Recommendation**: document packages as you add them—their public API and how they are consumed from `apps/`, `agents/`, and `workflows/`.

> _Spanish version: [README.es.md](./README.es.md)._

## Packages

| Package | Language | Contents | Used by |
| --- | --- | --- | --- |
| [`shared/`](./shared/README.md) | TypeScript | `@repo/shared-types`: TrackFlow domain types and pure utilities (Milestone 2) | `uis/script-automatizacion` |
| [`analisis-incidencias/`](./analisis-incidencias/README.md) | Python (standard library only) | Loading, validation, metrics and export of the CX incidents CSV ([`CONTEXT-incidencias.es.md`](../CONTEXT-incidencias.es.md)) | `scripts/analyze.py` and `services/api` |
