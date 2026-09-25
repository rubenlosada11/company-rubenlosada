# Carpeta `docs`

Esta carpeta contiene la **documentación transversal** del monorepo: guías de arquitectura, decisiones técnicas, convenciones, procesos, y cualquier material compartido entre aplicaciones, pipelines, agentes y workflows.

- **Propósito principal**: tener un punto único para la documentación “global” del proyecto (no específica de una sola app/agente).
- **Recomendación**: organiza la documentación por temas (arquitectura, despliegue, datos, seguridad, observabilidad, etc.) y mantén enlaces desde los READMEs de cada componente hacia estas guías.

## Documentos existentes

- [`hitos.md`](./hitos.md) — registro de los hitos completados, sus carpetas y sus demos públicas.
- [`ARCHITECTURE_PROPOSAL.md`](./ARCHITECTURE_PROPOSAL.md) — propuesta de arquitectura de backend (monolito
  modular FastAPI por dominios de negocio) para `services/api/`; aún no implementada.
