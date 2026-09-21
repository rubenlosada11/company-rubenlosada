# TrackFlow Website

Sitio web corporativo público de TrackFlow: presenta a la empresa, sus tres servicios, la cobertura en Estados
Unidos y España y el motivo para elegirla, y dirige a las marcas de e-commerce interesadas al formulario de
solicitud de información.

Next.js (App Router) + React + TypeScript + Tailwind CSS, con las mismas versiones y herramientas que
[`talent-pipeline-tracker`](../talent-pipeline-tracker/README.md). Sin backend ni librerías de estado.

> Este proyecto es independiente de [`../backoffice`](../backoffice/README.md): no comparten código.

## Fuente del contenido

Todo el texto sale de [`CONTEXT.es.md`](../../CONTEXT.es.md) y [`CONTEXT-trackflow.es.md`](../../CONTEXT-trackflow.es.md).
No hay clientes, logos, cifras, premios ni certificaciones inventados. Los datos viven en
[`lib/content.ts`](./lib/content.ts) (tipados); los componentes solo los pintan.

- **CTA “Solicitar información”:** enlaza al formulario ya existente de la landing
  (`https://landingtrackflow.rubenlosada.com/formulario/application.html`, ver
  [`../landing/README.md`](../landing/README.md)). No se duplica el formulario.
- **Ingresos anuales (~9 M€):** existen en el CONTEXT pero se decidió no publicarlos en la web.
- **Copy a revisar con Miguel Torres:** “Inventario en tiempo real” y “Tecnología propia para visibilidad total”
  proceden del briefing del Hito 1, aunque `CONTEXT.es.md` indica que hoy los dos almacenes no comparten inventario.

## Estructura

```text
website/
├── app/
│   ├── layout.tsx        # fuentes, metadatos, cabecera/pie, JSON-LD (Schema.org Organization)
│   ├── page.tsx          # ruta `/`: compone las secciones
│   ├── globals.css       # Tailwind + tokens
│   └── icon.png          # favicon
├── components/           # Hero, ValueProposition, Services, Process, Coverage, WhyTrackFlow,
│                         # Audience, Contact, SiteHeader/MobileNav, SiteFooter, ButtonLink, Icon…
├── lib/content.ts        # contenido y datos de contacto (fuente única del texto)
└── public/               # logo e imagen del hero (copiados de uis/landing)
```

## Ejecución local

```bash
cd uis/website
npm install
npm run dev      # http://localhost:3001
```

Producción local (también en el puerto 3001), un comando por línea:

```bash
npm run build
npm run start
```

> En Windows PowerShell 5.1 no uses `&&` para encadenar comandos (no lo admite): ejecútalos uno a uno o
> separados por `;`.

## Validación

```bash
npm run lint
npm run typecheck   # next typegen && tsc --noEmit
npm run build
```

No hay tests automatizados en el repo. Comprobación de la ruta `/` con la skill
[`validate-delivery`](../../.agents/skills/validate-delivery/SKILL.md):

```bash
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3001/ --expect "TrackFlow" --expect "Solicitar información"
```

## Accesibilidad y SEO

Landmarks (`header`, `nav`, `main`, `footer`), enlace “Saltar al contenido”, jerarquía `h1`→`h2`→`h3`, `alt` en
imágenes, foco visible, `lang="es"`, metadatos y Open Graph, y marcado Schema.org `Organization` (el exigido en el
briefing del Hito 1).
