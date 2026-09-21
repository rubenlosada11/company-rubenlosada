# Progress

> Registro vivo del estado del proyecto. **Actualizar antes de cada commit** en que cambie el estado, una
> decisión o el trabajo pendiente (ver `AGENTS.md`). Añadir entradas nuevas al principio de “Historial”; no
> reescribir el historial anterior.

## Estado actual (resumen)

- **Rama de trabajo:** `feature/agent-memory-bank` (desde `main` @ `50b77bd`).
- **Hito en curso:** Hito 4 — Ingeniería impulsada por IA.
- **Última actualización:** 2026-09-21.

| Componente | Estado |
| --- | --- |
| `memory-bank/` | ✅ Creado |
| `AGENTS.md` | ✅ Creado |
| `.agents/rules/project-conventions.md` | ✅ Creado (`scope: always`) |
| `.agents/skills/validate-delivery/` | ✅ Creada (`SKILL.md` + `check-route.mjs` + `check-hygiene.mjs`) |
| `uis/website` | ✅ Implementado y validado (`http://localhost:3001`) |
| `uis/backoffice` | ⏳ Pendiente |
| `services/` | ➖ No necesario (decisión documentada en `techContext.md`) |
| Pull Request a `main` | ⏳ Pendiente |

## Estado inicial (antes del Hito 4, `main` @ `50b77bd`)

- Hitos 1–3 entregados (ver `docs/hitos.md`): `uis/landing`, `packages/shared` + `uis/script-automatizacion`,
  `uis/talent-pipeline-tracker`.
- Sin `AGENTS.md`, sin memory bank, sin `.agents/`, sin `uis/website` ni `uis/backoffice`.
- Sin `CONTEXT.md` (el contexto está en `CONTEXT.es.md` y `CONTEXT-trackflow.es.md`).
- Sin `package.json` raíz, tests, CI, Docker ni backend.
- Git: sin `user.name`/`user.email` configurados en la máquina de trabajo.

## Historial

### 2026-09-21 — Hito 4 (sesión 1)

**Trabajo realizado**

- Inspección de git, remotos (`origin` = `rubenlosada11/company-rubenlosada`, no es un fork) y estructura.
- Creación de `memory-bank/` (`projectbrief.md`, `techContext.md`, `progress.md`).
- `AGENTS.md` en la raíz: lectura de inicio de sesión, flujo de 6 pasos previo a cada commit, áreas que requieren
  confirmación, mapa del repo y comandos reales.
- `.agents/rules/project-conventions.md` (`scope: always`).
- Skill `.agents/skills/validate-delivery/` con dos scripts Node sin dependencias
  (`check-route.mjs`: espera al servidor y valida HTTP 200 + contenido; `check-hygiene.mjs`: detecta ficheros
  generados/sensibles, cambios fuera de alcance y rama `main`).

**Validaciones (commit 1 — solo documentación y scripts)**

- `check-hygiene.mjs --allow memory-bank --allow AGENTS.md --allow .agents` → OK (exit 0).
- `check-hygiene.mjs --allow memory-bank` → FAIL esperado (detecta 5 ficheros fuera de alcance).
- `check-route.mjs http://localhost:3999/ --timeout 2` (sin servidor) → FAIL esperado (exit 1).
- No hay apps afectadas: lint/typecheck/build no aplican a este commit.

- `uis/website` (Next.js 16.3.4 + React 19.2.8 + Tailwind 4, npm). Ruta `/` con 8 secciones y componentes
  reutilizables: Hero (con datos clave), ValueProposition, Services (3), Process (4 pasos), Coverage (US/ES +
  carriers), WhyTrackFlow (4 beneficios), Audience, Contact; cabecera con menú móvil (`MobileNav`, único
  componente cliente), pie y JSON-LD `Organization`. Todo el texto vive en `lib/content.ts`.
- CTA “Solicitar información” → formulario existente de `uis/landing` (URL pública verificada: HTTP 200).
- Corrección en `check-route.mjs` (ver problemas resueltos).

**Validaciones (commit 2 — `uis/website`)**

- `npm run lint` → exit 0, sin errores.
- `npm run typecheck` (`next typegen && tsc --noEmit`) → exit 0.
- `npm run build` → OK; rutas `/` y `/icon.png` estáticas.
- `npm run start` (puerto 3001) + `check-route.mjs http://localhost:3001/` con 9 textos esperados → `OK 200`, 9/9,
  exit 0. Negativos: `/no-existe` → FAIL (404), servidor caído → FAIL.
- Navegador real (Edge headless vía playwright-core, fuera del repo), 1440×900 y 390×844: 0 errores/avisos de
  consola, 0 peticiones fallidas, 0 imágenes rotas, sin desborde horizontal, `lang="es"`, 1 `h1`, todas las
  imágenes con `alt`, menú móvil abre/cierra con los 4 enlaces + CTA. Inspección visual de la captura completa.
- No hay tests automatizados en el repo (no aplica).

**Problemas encontrados**

- `check-route.mjs` daba un falso positivo: “This page could not be found” aparece siempre dentro del payload RSC
  (`<script>`) de Next.js aunque la página sea 200.
- `check-route.mjs` terminaba con `Assertion failed: UV_HANDLE_CLOSING` (exit -1073740791) en Windows al usar
  `process.exit()` tras `fetch`, devolviendo un código erróneo en un caso de éxito.
- `CONTEXT.md` no existe → se usa `CONTEXT.es.md` (+ `CONTEXT-trackflow.es.md`). Documentado.
- El CONTEXT nombra al CEO de dos formas distintas (Thomas Harry / Daniel Espinoza) → no se muestra en ninguna UI.
- Git sin identidad configurada → se usará identidad por comando, sin tocar la configuración global.

**Problemas resueltos**

- Los textos prohibidos de `check-route.mjs` se buscan ahora solo en el HTML visible (sin bloques `<script>`).
- `check-route.mjs` usa `process.exitCode` en lugar de `process.exit()`; verificado: OK → 0, 404 → 1, servidor
  caído → 1.
- Los tres últimos puntos de “Problemas encontrados” quedan mitigados (ver decisiones en `techContext.md`).

## Trabajo pendiente

Se completa al cerrar el hito.

## Siguientes pasos

Se completa al cerrar el hito.
