# Carpeta `services`

Esta carpeta contiene **todos los servicios backend** (APIs y workers en segundo plano) relacionados con la compañía para el proyecto transversal de AI Engineering.

Cada subcarpeta dentro de `services/` debe corresponder a **un servicio concreto** (por ejemplo `admin-api`, `data-processor-worker`) e incluir su propia documentación técnica y funcional.

- **Propósito principal**: centralizar toda la lógica backend, APIs y consumidores de colas que dan soporte a los casos de uso de la compañía.
- **Recomendación**: documenta en este archivo (o en sub-READMEs) los servicios que vayas añadiendo, su objetivo, tecnología usada y cómo ejecutarlos.

## Servicios

| Servicio | Tecnología | Propósito |
| --- | --- | --- |
| [`api/`](./api/README.md) | FastAPI + Pydantic + TinyDB (Python, uv) | Directorio de proveedores (`/suppliers`): fuente única de verdad de los proveedores de TrackFlow en USA y España; y analizador de incidencias de CX (`/api/incidents`): validación, métricas y exportación a CSV del fichero de incidencias del helpdesk, con `packages/analisis-incidencias`; y gestor de incidencias (también en `/api/incidents`): registro, listado con filtros, cambio de estado y resumen. Los consume el backoffice. Rutas protegidas con JWT. Solo local. |
