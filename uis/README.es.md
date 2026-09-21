# Carpeta `uis`

Esta carpeta contiene **todos los proyectos con interfaz de usuario** para el proyecto transversal de AI Engineering de la compañía — por ejemplo: un sitio web público, un frontend de panel de administración, una interfaz de ecommerce, portales para clientes, aplicaciones Streamlit/Gradio u otras herramientas sólo-frontend.

Los dos proyectos principales que se almacenan aquí son:

- **`landing`** — la landing page pública de la compañía (presentación y captación).
- **`backoffice`** — la aplicación interna de administración. Es el lugar ideal para desarrollar múltiples soluciones dentro de un mismo proyecto: autenticación, gestión de personas, gestión de operaciones, comunicación interna y otras capacidades de back-office.

Organiza `uis/` por **distintas áreas de la compañía** — cada subcarpeta agrupa un ámbito diferente (por ejemplo, web pública frente a operaciones internas) e incluye su propia documentación técnica y funcional.

- **Propósito principal**: centralizar en un único lugar todas las aplicaciones frontend que dan soporte a los casos de uso de la compañía.
- **Recomendación**: documenta en este archivo (o en sub-READMEs) las aplicaciones que vayas añadiendo, su objetivo, tecnología usada y cómo ejecutarlas.

> _These instructions are also available in [English](./README.md)._

## Implementaciones actuales

- `landing/`: landing page de TrackFlow con Tailwind compilado localmente (`tailwind.css`), navegacion, hero, beneficios, CTA de contacto y footer.
- `formulario/`: formulario de aplicacion/registro de TrackFlow conectado desde la landing.
- `script-automatizacion/`: interfaz de prueba manual para las utilidades de procesamiento de datos de `packages/shared` (filtrado, ordenamiento, búsqueda lineal/binaria, agregaciones y validaciones sobre envíos, transportistas, devoluciones y clientes). Ver [`script-automatizacion/README.md`](./script-automatizacion/README.md).
- `talent-pipeline-tracker/`: aplicación Next.js interna de People & Talent para gestionar el pipeline de candidaturas de TrackFlow (listado con filtros/búsqueda, detalle, cambio de estado/etapa, notas, creación y edición), consumiendo la API pública de Talent Tracker. Ver [`talent-pipeline-tracker/README.md`](./talent-pipeline-tracker/README.md).

- `website/`: sitio web corporativo público de TrackFlow (Next.js + Tailwind): hero, servicios, flujo de entrega, cobertura EE. UU./España, beneficios, público objetivo y contacto, con marcado Schema.org. Su contenido sale de `CONTEXT.es.md` y su CTA apunta al formulario existente en `landing/formulario/`. Ver [`website/README.md`](./website/README.md).

### Ejecutar la landing localmente

Desde `uis/`:

```bash
npx serve . -l 8080
```

Luego abre `http://localhost:8080/landing/`.

Para ir al formulario directamente: `http://localhost:8080/formulario/application.html`.

### Ejecutar la demo de scripts de automatización

Desde la raíz del repo:

```bash
npx http-server . -p 3000
```

Luego abre `http://localhost:3000/uis/script-automatizacion/`.

### Ejecutar el website

Desde `uis/website/`:

```bash
npm install
npm run dev
```

Luego abre `http://localhost:3001`. Más detalle en [`website/README.md`](./website/README.md).

### Ejecutar el Talent Pipeline Tracker

Desde `uis/talent-pipeline-tracker/`:

```bash
npm install
npm run dev
```

Luego abre `http://localhost:3000`. Más detalle en [`talent-pipeline-tracker/README.md`](./talent-pipeline-tracker/README.md).
