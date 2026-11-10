# Carpeta `docs`

Esta carpeta contiene la **documentación transversal** del monorepo: guías de arquitectura, decisiones técnicas, convenciones, procesos, y cualquier material compartido entre aplicaciones, pipelines, agentes y workflows.

- **Propósito principal**: tener un punto único para la documentación “global” del proyecto (no específica de una sola app/agente).
- **Recomendación**: organiza la documentación por temas (arquitectura, despliegue, datos, seguridad, observabilidad, etc.) y mantén enlaces desde los READMEs de cada componente hacia estas guías.

## Documentos existentes

- [`hitos.md`](./hitos.md) — registro de los hitos completados, sus carpetas y sus demos públicas.
- [`ARCHITECTURE_PROPOSAL.md`](./ARCHITECTURE_PROPOSAL.md) — propuesta de arquitectura de backend (monolito
  modular FastAPI por dominios de negocio) para `services/api/`; aún no implementada.
- [`analizador-incidencias.md`](./analizador-incidencias.md) — analizador del CSV de incidencias de CX: script,
  API, página del backoffice, reglas de validación, métricas y decisiones.
- [`pruebas-analizador-incidencias.md`](./pruebas-analizador-incidencias.md) — registro de pruebas del analizador.
- [`gestor-incidencias.md`](./gestor-incidencias.md) — gestor de incidencias centralizado: modelo, seed del CSV
  histórico, endpoints, páginas del backoffice, manejo de errores, tests y limitaciones.
- [`inventario.md`](./inventario.md) — Hito 5, gestión de inventario backend: API `/inventory` con SQLModel,
  equivalencia con la estructura del briefing, reglas de stock por almacén, datos semilla, Supabase y limitaciones.
- [`telemetry/telemetry-plan.md`](./telemetry/telemetry-plan.md) y
  [`telemetry/event-schemas.json`](./telemetry/event-schemas.json) — plan de telemetría (diseño): 43 eventos,
  envelope, allowlists, privacidad y retención (JSON Schema validable).
- [`telemetry/telemetry-capture.md`](./telemetry/telemetry-capture.md) — captura de telemetría: `TelemetryService`
  del backoffice (`track()`, lotes, reintentos, `sendBeacon`), receptor temporal `POST /telemetry/events`, eventos
  instrumentados, variables, pruebas y limitaciones.
- [`docker.md`](./docker.md) — Docker del monorepo: contenedores `interfaces` (website + backoffice) y `backend`
  (API), Compose de desarrollo con hot reload y de producción, variables, despliegue en el VPS sin acceso público,
  actualización, vuelta atrás y problemas habituales.
- [`despliegue-api.md`](./despliegue-api.md) — instrucciones (no ejecutadas) para desplegar `services/api` y conectar
  el backoffice de producción: tarball, `uv`, variables, proxy, autenticación y verificación.
