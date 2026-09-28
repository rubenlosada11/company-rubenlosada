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
- [`despliegue-api.md`](./despliegue-api.md) — deployment instructions (not executed) for `services/api` and the
  production backoffice: tarball, `uv`, variables, proxy, authentication and checks (in Spanish).
