# TrackFlow Backoffice

Aplicación interna de TrackFlow Tech. Muestra la estructura del negocio, el backlog de iniciativas de TrackFlow
Tech y el estado de los hitos del proyecto, **a partir del contexto de empresa** (no hay conexión con sistemas
reales).

Next.js (App Router) + React + TypeScript + Tailwind CSS, con las mismas versiones y herramientas que
[`talent-pipeline-tracker`](../talent-pipeline-tracker/README.md). Sin backend ni librerías de estado.

> Este proyecto es independiente de [`../website`](../website/README.md): layout, estilos y datos propios; no
> comparten código.

## Qué muestra la ruta `/`

| Sección | Contenido | Fuente |
| --- | --- | --- |
| Resumen | Datos de partida del briefing (empleados, almacenes, transportistas, % de devoluciones y de consultas automatizables, facturación) y resumen del backlog calculado a partir de los datos (áreas, iniciativas, por estado). | `CONTEXT.es.md` |
| Áreas de negocio | Las 7 áreas, con responsable, equipo y situación actual. Cada tarjeta filtra las iniciativas de su área. | `CONTEXT.es.md` |
| Iniciativas | 33 necesidades de las áreas (“Qué necesitan”) con filtros por área y estado, contador y estado vacío. Estados: *Necesidad identificada* / *Base técnica disponible* (3 iniciativas que ya tienen base en `packages/shared`, Hito 2). | `CONTEXT.es.md` + `packages/shared` |
| Hitos del proyecto | Hitos 1–4 con ubicación en el monorepo y demo pública. | `docs/hitos.md` |

**No hay métricas en vivo ni datos inventados.** Las cifras son las del briefing, etiquetadas como tal. El nombre
del CEO no se muestra porque `CONTEXT.es.md` lo cita de dos formas distintas (ver
[`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md)).

## Estructura

```text
backoffice/
├── app/
│   ├── layout.tsx        # layout propio: sidebar + barra superior; `noindex` (herramienta interna)
│   ├── page.tsx          # ruta `/`
│   └── globals.css
├── components/           # Sidebar, Topbar, Overview, Explorer (cliente: filtros), AreaCard, Milestones,
│                         # PageSection, StatCard, Badge
├── lib/
│   ├── data/             # areas.ts, initiatives.ts, milestones.ts, baseline.ts (datos tipados derivados del CONTEXT)
│   ├── initiatives.ts    # lógica pura: filterInitiatives, countByArea, countByStatus
│   └── nav.ts
├── types/index.ts        # BusinessArea, Initiative, Milestone, BaselineFact
└── public/logo/          # logo (copiado de uis/landing)
```

## Ejecución local

```bash
cd uis/backoffice
npm install
npm run dev      # http://localhost:3002
```

Producción local: `npm run build && npm run start` (también en el puerto 3002).

## Validación

```bash
npm run lint
npm run typecheck   # next typegen && tsc --noEmit
npm run build
```

No hay tests automatizados en el repo. Comprobación de la ruta `/` con la skill
[`validate-delivery`](../../.agents/skills/validate-delivery/SKILL.md):

```bash
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/ --expect "Backoffice" --expect "Áreas de negocio"
```

## Pendiente / fuera de alcance

- **Sin autenticación:** solo muestra información del briefing, pero no debe publicarse abiertamente hasta
  que exista un control de acceso (el layout ya lleva `noindex`).
- Sin conexión a datos reales (inventario, envíos, devoluciones…): llegará con `services/` y los pipelines de
  `data/` cuando existan.
- Mantener `lib/data/` sincronizado con `CONTEXT.es.md` y `docs/hitos.md` cuando cambien.
