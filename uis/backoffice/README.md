# TrackFlow Backoffice

Aplicación interna de TrackFlow Tech. Muestra la estructura del negocio, el backlog de iniciativas de TrackFlow
Tech y el estado de los hitos del proyecto **a partir del contexto de empresa** (ruta `/`), y el **directorio de
proveedores** conectado a la API [`services/api`](../../services/api/README.md) (ruta `/proveedores`).

Next.js (App Router) + React + TypeScript + Tailwind CSS, con las mismas versiones y herramientas que
[`talent-pipeline-tracker`](../talent-pipeline-tracker/README.md). Sin librerías de estado ni de UI.

> Este proyecto es independiente de [`../website`](../website/README.md): layout, estilos y datos propios; no
> comparten código.

## Demo pública

- URL: https://backofficetrackflow.rubenlosada.com/
- Publicada **sin autenticación**: solo muestra datos del briefing (ficticios, ejercicio de bootcamp) y lleva
  `noindex`. Ver “Pendiente / fuera de alcance”.

## Qué muestra la ruta `/`

| Sección | Contenido | Fuente |
| --- | --- | --- |
| Resumen | Datos de partida del briefing (empleados, almacenes, transportistas, % de devoluciones y de consultas automatizables, facturación) y resumen del backlog calculado a partir de los datos (áreas, iniciativas, por estado). | `CONTEXT.es.md` |
| Áreas de negocio | Las 7 áreas, con responsable, equipo y situación actual. Cada tarjeta filtra las iniciativas de su área. | `CONTEXT.es.md` |
| Iniciativas | 33 necesidades de las áreas (“Qué necesitan”) con filtros por área y estado, contador y estado vacío. Estados: *Necesidad identificada* / *Base técnica disponible* (3 iniciativas que ya tienen base en `packages/shared`, Hito 2). | `CONTEXT.es.md` + `packages/shared` |
| Hitos del proyecto | Hitos 1–4 con ubicación en el monorepo y demo pública. | `docs/hitos.md` |

**No hay métricas en vivo ni datos inventados.** Las cifras son las del briefing, etiquetadas como tal. Como CEO
figura Thomas Harry (fundador y CEO), por decisión del desarrollador: `CONTEXT.es.md` también cita a Daniel Espinoza
(ver [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md)).

## Qué muestra la ruta `/proveedores`

Directorio de proveedores de [`CONTEXT-directorio.md`](../../CONTEXT-directorio.md) para Carlos Vega (Carrier
Operations). Todos los datos salen de la API; nada está escrito en el frontend.

| Función | Llamada a la API |
| --- | --- |
| Listado (nombre, zona, email, notas, país, categorías, tarifa, estado, fecha de la última tarifa) | `GET /suppliers` |
| Filtros por país y por categoría, combinables, sin recargar la página | `GET /suppliers?country=…&category=…` |
| Alta con validación en cliente; los errores 422 de FastAPI se muestran junto a su campo. La moneda la fija el país | `POST /suppliers` |
| Editar la tarifa en la fila (estado “Guardando…”, error en la fila, valor y fecha actualizados al momento) | `PATCH /suppliers/{id}/rate` |
| Suspender / reactivar desde la fila; estado con badge verde (activo) o ámbar (suspendido) | `PATCH /suppliers/{id}/status` |

Capturas con filtros aplicados: [España + Carrier de última milla](./screenshots/screenshot%20proveedores%20filtro1.png)
(4 proveedores) y [España](./screenshots/screenshot%20proveedores%20filtro2.png) (6 proveedores).

No hay botón de eliminar: el flujo de TrackFlow es suspender a los proveedores, no borrarlos. Si la API no responde
o falta la variable `NEXT_PUBLIC_API_BASE_URL`, la página muestra un aviso con el motivo y un botón “Reintentar”.

## Estructura

```text
backoffice/
├── app/
│   ├── layout.tsx        # layout propio: sidebar + barra superior; `noindex` (herramienta interna)
│   ├── page.tsx          # ruta `/`
│   ├── proveedores/page.tsx  # ruta `/proveedores`
│   └── globals.css
├── components/           # Sidebar, Topbar, NavLink (cliente: enlace activo), Overview, Explorer (cliente: filtros),
│                         # AreaCard, Milestones, PageSection, StatCard, Badge,
│                         # SupplierDirectory, SupplierForm, SupplierRow (cliente: directorio de proveedores)
├── lib/
│   ├── data/             # areas.ts, initiatives.ts, milestones.ts, baseline.ts, suppliers.ts (valores del CONTEXT)
│   ├── initiatives.ts    # lógica pura: filterInitiatives, countByArea, countByStatus
│   ├── http.ts           # cliente HTTP de la API (errores 422 de FastAPI por campo)
│   ├── suppliers.ts      # llamadas a /suppliers, validación del formulario y formato de tarifas y fechas
│   └── nav.ts
├── types/index.ts        # BusinessArea, Initiative, Milestone, BaselineFact, Supplier…
├── .env.example          # NEXT_PUBLIC_API_BASE_URL
└── public/logo/          # logo (copiado de uis/landing)
```

## Ejecución local

```bash
cd uis/backoffice
npm install
npm run dev      # http://localhost:3002
```

Para `/proveedores` hace falta la API arrancada ([`services/api`](../../services/api/README.md), puerto 8000) y la
URL en `.env.local` (Next.js la incrusta al compilar: tras cambiarla, reinicia `npm run dev` o repite el build). En
Windows PowerShell:

```powershell
Copy-Item .env.example .env.local
```

Producción local (también en el puerto 3002), un comando por línea:

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
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/ --expect "Backoffice" --expect "Áreas de negocio"
```

## Pendiente / fuera de alcance

- **Sin autenticación:** hoy está publicada abierta (https://backofficetrackflow.rubenlosada.com/). Solo muestra
  información del briefing, que es ficticia, y el layout lleva `noindex`. Antes de mostrar datos reales hay que
  protegerla (p. ej. Basic Auth en el proxy o un login en la app).
- **`/proveedores` en producción:** la API solo corre en local, así que en la demo pública la página muestra el
  aviso “Falta la variable NEXT_PUBLIC_API_BASE_URL”. Publicar la API exigiría antes autenticación, porque permite
  editar tarifas y estados.
- Sin conexión a otros datos reales (inventario, envíos, devoluciones…): llegará con `services/` y los pipelines de
  `data/` cuando existan.
- Mantener `lib/data/` sincronizado con `CONTEXT.es.md` y `docs/hitos.md` cuando cambien.
