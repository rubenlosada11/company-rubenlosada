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
- `script-automatizacion/`: manual test interface for the `packages/shared` data-processing utilities (filtering, sorting, linear/binary search, aggregations and validations over shipments, carriers, returns and clients). See [`script-automatizacion/README.md`](./script-automatizacion/README.md).
- `talent-pipeline-tracker/`: internal Next.js app for TrackFlow's People & Talent team to manage the candidate pipeline (filterable/searchable list, detail view, status/stage changes, notes, create and edit), backed by the public Talent Tracker API. See [`talent-pipeline-tracker/README.md`](./talent-pipeline-tracker/README.md).

- `website/`: TrackFlow's public corporate website (Next.js + Tailwind): hero, services, delivery flow, US/Spain coverage, benefits, target audience and contact, with Schema.org markup. Its content comes from `CONTEXT.es.md` and its CTA points to the existing lead form in `landing/formulario/`. See [`website/README.md`](./website/README.md).

### Run The Landing Page Locally

From `uis/`:

```bash
npx serve . -l 8080
```

Then open `http://localhost:8080/landing/`.

To open the form directly: `http://localhost:8080/formulario/application.html`.

### Run The Data-Processing Demo Locally

From the repo root:

```bash
npx http-server . -p 3000
```

Then open `http://localhost:3000/uis/script-automatizacion/`.

### Run The Website Locally

From `uis/website/`:

```bash
npm install
npm run dev
```

Then open `http://localhost:3001`. More detail in [`website/README.md`](./website/README.md).

### Run The Talent Pipeline Tracker Locally

From `uis/talent-pipeline-tracker/`:

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`. More detail in [`talent-pipeline-tracker/README.md`](./talent-pipeline-tracker/README.md).
