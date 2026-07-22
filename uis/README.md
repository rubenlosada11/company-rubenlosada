# `uis` folder

This folder contains **all projects with a user interface** for the cross-functional AI Engineering company project — for example: a public website, admin dashboard frontend, ecommerce UI, customer portals, Streamlit/Gradio app or other frontend-only tools.

The two main projects stored here are:

- **`landing`** — the company's public landing page (presentation and lead capture).
- **`backoffice`** — the internal admin application. This is the ideal place to develop multiple solutions within a single project: authentication, people management, operations management, internal communication, and other back-office capabilities.

Organize `uis/` by **different concerns** — each subfolder covers a distinct area of the company (for example, public web vs internal operations) and includes its own technical and functional documentation.

- **Main purpose**: to centralize in a single place all frontend applications that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the applications you add, their objective, the technology used, and how to run them.

> _Estas instrucciones también están disponibles en [español](./README.es.md)._

## Current Implementations

- `landing/`: TrackFlow landing page built with locally compiled Tailwind CSS (`tailwind.css`), navigation, hero section, key benefits, contact CTA, and professional footer.
- `formulario/`: TrackFlow application/registration form linked from the landing page.

### Run The Landing Page Locally

From `uis/`:

```bash
npx serve . -l 8080
```

Then open `http://localhost:8080/landing/`.

To open the form directly: `http://localhost:8080/formulario/application.html`.
