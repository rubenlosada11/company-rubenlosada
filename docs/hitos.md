# Hitos completados — TrackFlow

Registro de los hitos entregados en este proyecto transversal, con sus carpetas y demos públicas. Contexto de
negocio completo en [`CONTEXT.es.md`](../CONTEXT.es.md) y [`CONTEXT-trackflow.es.md`](../CONTEXT-trackflow.es.md).

## Hito 1 — Sitio Web Público

| | |
| --- | --- |
| Carpetas | [`uis/landing/`](../uis/landing/), [`uis/landing/formulario/`](../uis/landing/formulario/) |
| Descripción | Landing comercial de TrackFlow (servicios, cobertura US/ES, contacto) + formulario de captación de leads con validación completa en cliente, Tailwind compilado localmente, Schema.org. |
| Demo pública | [landingtrackflow.rubenlosada.com](https://landingtrackflow.rubenlosada.com/) |
| Detalle | [`uis/landing/README.md`](../uis/landing/README.md) |

## Hito 2 — Scripts de automatización y procesamiento de datos

| | |
| --- | --- |
| Carpetas | [`packages/shared/`](../packages/shared/) (tipos y utilidades), [`uis/script-automatizacion/`](../uis/script-automatizacion/) (interfaz de prueba manual) |
| Descripción | Modelado de las entidades de dominio de TrackFlow (`Carrier`, `Client`, `Shipment`, `ReturnRequest`) y utilidades TypeScript puras y tipadas: filtrado multicriterio, ordenamiento inmutable, búsqueda lineal y binaria, agregaciones/reportes de negocio (coste por kg, tasa de entrega a tiempo, devoluciones por motivo, clientes a renovar) y validaciones con `{ valid, errors[] }`. |
| Demo pública | [scriptsautotrackflow.rubenlosada.com](https://scriptsautotrackflow.rubenlosada.com/) |
| Detalle | [`packages/shared/README.md`](../packages/shared/README.md), [`uis/script-automatizacion/README.md`](../uis/script-automatizacion/README.md) |

## Hito 3 — Talent Pipeline Tracker

| | |
| --- | --- |
| Carpeta | [`uis/talent-pipeline-tracker/`](../uis/talent-pipeline-tracker/) |
| Descripción | Aplicación Next.js (App Router, TypeScript, Tailwind, sin librerías de estado externas) para People & Talent: listado de candidaturas con filtros por estado/etapa (query params) y búsqueda en cliente, detalle con cambio de estado/etapa y gestión de notas (crear/eliminar), y formularios de creación y edición. Consume directamente la API pública de [Talent Tracker](https://playground.4geeks.com/tracker/api/v1/docs) (`GET/POST/PUT/PATCH/DELETE /records`, notas). |
| Demo pública | [talent-pipeline-tracker.rubenlosada.com](https://talent-pipeline-tracker.rubenlosada.com/) |
| Detalle | [`uis/talent-pipeline-tracker/README.md`](../uis/talent-pipeline-tracker/README.md) |
