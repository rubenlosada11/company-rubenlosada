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

### Ejecutar la landing localmente

Desde `uis/`:

```bash
npx serve . -l 8080
```

Luego abre `http://localhost:8080/landing/`.

Para ir al formulario directamente: `http://localhost:8080/formulario/application.html`.
