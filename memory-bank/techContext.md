# Tech Context

> Estado técnico **real** del monorepo, verificado inspeccionando el repositorio (no la plantilla). Actualizar
> cuando cambie el stack, un comando o una convención.

## Estructura del monorepo

Monorepo de plantilla 4Geeks (una carpeta por responsabilidad; cada carpeta tiene su `README.md`/`README.es.md`).
**No hay runner de workspace** (sin `package.json` raíz, sin lockfile raíz, sin Turborepo/Nx/pnpm): cada proyecto
JS es autónomo, con su propio `package.json` y `package-lock.json`, y se opera desde su carpeta.

| Carpeta | Contenido real hoy |
| --- | --- |
| `uis/landing/` | Hito 1. HTML estático + Tailwind compilado (`tailwind.css`) + formulario de leads con `validation.js`. Servir con `npx serve . -l 8080` desde `uis/`. |
| `uis/script-automatizacion/` | Hito 2. Interfaz de prueba manual (HTML + TS/JS) de `packages/shared`. |
| `uis/talent-pipeline-tracker/` | Hito 3. **Next.js** (App Router). Referencia de convenciones para apps nuevas. |
| `uis/website/` | Hito 4. Web corporativa pública (Next.js). |
| `uis/backoffice/` | Hito 4. Aplicación interna (Next.js). |
| `packages/shared/` | `@repo/shared-types`: tipos de dominio (`Carrier`, `Shipment`, `ReturnRequest`, `Client`) y utilidades TS puras. `dist/` está versionado. |
| `services/` | **Solo README.** No existe backend en el repo. |
| `agents/`, `skills/`, `mcps/`, `workflows/`, `data/`, `infra/`, `scripts/`, `internal/`, `shared/` | Solo README/plantillas (`agents/_template`, `skills/_template`). |
| `docs/` | `hitos.md` (registro de hitos) + READMEs. |
| `memory-bank/`, `AGENTS.md`, `.agents/` | Infraestructura para agentes (Hito 4). |

No existen: `docker-compose.yml`, CI/CD (`.github/`), tests automatizados, `Dockerfile`, base de datos.
El `.gitignore` raíz solo contiene `node_modules/`; cada app Next.js tiene el suyo.

## Stack

- **Lenguaje:** TypeScript 5 (estricto) en todo el código nuevo. `packages/shared` compila con `tsc` (ESM).
- **Package manager:** **npm** (`package-lock.json` por proyecto). Node 24 / npm 11 en la máquina del desarrollador.
- **Frontend (apps Next.js):** Next.js **16.3.4** (App Router), React **19.2.8**, Tailwind CSS **4**
  (`@tailwindcss/postcss`, `@import "tailwindcss"` en `app/globals.css`), ESLint 9 flat config con
  `eslint-config-next` (`core-web-vitals` + `typescript`), alias `@/*` → raíz de la app. Sin librerías de estado
  externas: hooks de React. Fuentes vía `next/font/google`.
- **Backend:** ninguno. La única API consumida es la pública de Talent Tracker
  (`https://playground.4geeks.com/tracker/api/v1`, solo la usa `talent-pipeline-tracker`).
- **Diseño (identidad ya establecida en landing y tracker):** fuentes **Archivo** (títulos, `font-heading`) y
  **Manrope** (cuerpo, `font-body`); primario `blue-700`, neutros `slate`, pie `blue-950`; contenedor
  `w-[min(1120px,92vw)]`; eyebrow `text-xs font-bold uppercase tracking-[0.17em] text-blue-800`; botones
  redondeados `rounded-full`. Logo: `TrackFlow_Logo1_Full.png` (1190×264); favicon: `TrackFlow_Favicon.png`
  (en `uis/landing/`; las apps Next.js lo copian a `public/logo/` y `app/icon.png`).

## Puertos locales (convención)

| App | Puerto | Nota |
| --- | --- | --- |
| `uis/talent-pipeline-tracker` | 3000 | `next dev` por defecto |
| `uis/website` | **3001** | fijado en los scripts (`-p 3001`) |
| `uis/backoffice` | **3002** | fijado en los scripts (`-p 3002`) |
| `uis/landing` | 8080 | `npx serve` |

Se fijan puertos distintos para poder arrancar `website` y `backoffice` a la vez (validación y capturas).

## URLs de producción

Cada uis desplegada lleva un `LINK_PRODUCCION.md` y una sección “Demo pública” en su README; el registro global está
en `docs/hitos.md`. Todas cuelgan de subdominios de `rubenlosada.com` (website y backoffice responden con la
cabecera `server: cloudflare`).

| App | URL |
| --- | --- |
| `uis/landing` | https://landingtrackflow.rubenlosada.com/ |
| `uis/script-automatizacion` | https://scriptsautotrackflow.rubenlosada.com/ |
| `uis/talent-pipeline-tracker` | https://talent-pipeline-tracker.rubenlosada.com/ |
| `uis/website` | https://websitetrackflow.rubenlosada.com/ |
| `uis/backoffice` | https://backofficetrackflow.rubenlosada.com/ (**sin autenticación**, con `noindex`) |

Método de despliegue indicado al agente del servidor para website y backoffice: extraer exactamente `uis/website` y
`uis/backoffice` del tarball de GitHub (`codeload.github.com/rubenlosada11/company-rubenlosada/tar.gz/main`) en la
carpeta de cada sitio y ejecutar `npm ci --include=dev` y `npm run build` (necesita Node ≥ 20.9). Al añadir una nueva
uis desplegada: `LINK_PRODUCCION.md`, sección en su README y fila en `docs/hitos.md`.

## Comandos

Ejecutar **desde la carpeta de cada app** (`cd uis/<app>`):

| Acción | Comando | Disponible en |
| --- | --- | --- |
| Instalar | `npm install` | todos los proyectos JS |
| Desarrollo | `npm run dev` | tracker, website, backoffice |
| Lint | `npm run lint` (`eslint`) | tracker, website, backoffice |
| Typecheck | `npm run typecheck` (`tsc --noEmit`) | website, backoffice, `packages/shared` |
| Build | `npm run build` | tracker, website, backoffice, `packages/shared` |
| Producción local | `npm run start` | tracker, website, backoffice |
| Demo de utilidades | `npm run demo` (en `packages/shared`) | `packages/shared` |

**Shell del desarrollador: Windows PowerShell 5.1.** No admite `&&`/`||` ni la continuación de línea `\`.
En documentación y comandos que se le den al desarrollador: **un comando por línea** (o separados por `;`) y
`cd uis\website` (rutas relativas desde la raíz del repo). Los `&&` dentro de los `scripts` de `package.json` sí
funcionan (npm los ejecuta con `cmd.exe`).

`talent-pipeline-tracker` no tiene script `typecheck` (el tipado se comprueba en `next build`); no se ha tocado.
**Tests:** no hay ninguno en el repo (ni runner instalado). Está fuera del alcance introducir uno sin acordarlo.

## Convenciones arquitectónicas

- **Regla de ubicación** (`README.es.md` raíz): interfaz visual → `uis/`; API/segundo plano → `services/`; datos →
  `data/`; trabajo de un modelo → `agents/` (+ `skills/`/`mcps/`); código compartido por 2+ carpetas → `packages/`.
- Cada app/servicio nuevo lleva **subcarpeta + README** (y se lista en `uis/README.md`/`uis/README.es.md`).
- **Una app = un proyecto independiente.** `uis/website` y `uis/backoffice` no importan código entre sí. Si hace
  falta compartir algo, se extrae a `packages/` (decisión que requiere confirmación).
- Estructura de app Next.js (patrón del tracker): `app/` (rutas), `components/`, `lib/`, `types/`, `public/`.
  Los datos derivados del CONTEXT viven en módulos TS tipados (`lib/`), no en JSX.
- Documentación en **español**; READMEs de carpeta suelen ser bilingües (`README.md` + `README.es.md`), y los de
  apps de hitos (tracker) solo `README.md` en español.
- Componentes de servidor por defecto; `"use client"` solo donde hay estado/eventos.

## Decisiones técnicas del Hito 4

| Decisión | Motivo |
| --- | --- |
| `website` y `backoffice` en **Next.js 16 + Tailwind 4 + TS**, mismas versiones que el tracker | Es el único framework de app ya presente; “no introducir un framework alternativo”. La `landing` estática es de hito 1 y no se reutiliza como base. |
| Sin `/services` ni backend | Las dos UIs cumplen el requisito con datos derivados del CONTEXT; un backend sería artificial. |
| CTA del website → formulario existente de `uis/landing/formulario/` (URL pública documentada en `uis/landing/README.md`) | No duplicar el formulario de captación. |
| Backoffice con datos tipados en `lib/`, sin métricas en vivo | El CONTEXT no aporta métricas en tiempo real. Solo se muestran hechos documentados, etiquetados como “datos de partida”. |
| Skill en `.agents/skills/validate-delivery/` (no en `skills/`) | Ubicación exigida por el hito; `skills/` (plantilla 4Geeks) queda para skills de dominio. Mismo formato `SKILL.md`. |
| `AGENTS.md` en la raíz | Las apps Next.js ignoran su propio `AGENTS.md` generado por `next dev` (regla ya presente en el `.gitignore` del tracker); el de la raíz es el protocolo del repo. |
| Fichero de contexto = `CONTEXT.es.md` | `CONTEXT.md` no existe. Se referencia el real; no se crea duplicado. |
| Script `typecheck` añadido en apps nuevas | Permite el flujo lint → typecheck → build definido en `AGENTS.md` (patrón ya usado en `packages/shared`). |

## Restricciones y cosas que el agente NO debe cambiar unilateralmente

- `CONTEXT.es.md` y `CONTEXT-trackflow.es.md` (fuente de verdad del negocio).
- Versiones mayores de `next`, `react`, `tailwindcss`, `typescript`, `eslint` (alineadas con el tracker).
- El framework/estilo de cada app existente (`landing` estática, `script-automatizacion`, tracker).
- La identidad visual (fuentes, paleta, logo) y el idioma base (español).
- La estructura de carpetas de primer nivel y su responsabilidad.
- `packages/shared` (`dist/` versionado; cambios de tipos afectan a hitos previos).
- Secretos, `.env*` (solo `.env.example` se versiona), credenciales, despliegue, DNS/dominios `rubenlosada.com`.
- Añadir CI/CD, Docker, workspace raíz o backend: requiere confirmación.
