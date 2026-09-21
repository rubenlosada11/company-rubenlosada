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
| `uis/backoffice` | ✅ Implementado y validado (`http://localhost:3002`) |
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

- `uis/backoffice` (misma base técnica que el website, puerto 3002). Layout propio (sidebar + barra superior,
  `noindex`) y ruta `/` con: Resumen (datos de partida del briefing + resumen del backlog calculado), Áreas de
  negocio (7), Iniciativas (33, filtros por área y estado, contador, estado vacío) e Hitos (1–4). Datos tipados
  en `lib/data/`, lógica pura en `lib/initiatives.ts`, único componente cliente: `Explorer`.
- 3 iniciativas marcadas “Base técnica disponible” (dashboard de transportistas, dashboard de devoluciones,
  alertas de vencimiento) porque `packages/shared` (Hito 2) ya tiene el cálculo; se verificó en el código que
  `clientsNearContractRenewal` admite umbral configurable pero no envía alertas.
- Sin nombre de CEO en la UI (inconsistencia del CONTEXT).

**Validaciones (commit 3 — `uis/backoffice`)**

- `npm run lint` → exit 0. `npm run typecheck` → exit 0. `npm run build` → OK, `/` estática.
- `npm run start` (3002) + `check-route.mjs http://localhost:3002/` con 6 textos esperados → `OK 200`, 6/6, exit 0.
  Salida del servidor sin errores.
- Navegador real (Edge headless, 24 comprobaciones): contador inicial 33/33; filtro por área (almacén → 4);
  filtro por estado (base técnica → 3); combinación sin resultados → estado vacío; botón de tarjeta de área
  (CX → 6) sincroniza el select y `aria-pressed`; segundo clic desactiva el filtro; responsables y datos visibles;
  sin nombre de CEO; 1 `h1`; `meta robots noindex`; sin desborde horizontal en 1440 px y 390 px; móvil con nav
  superior de 4 enlaces y sidebar oculta; 0 errores de consola/red. Inspección visual de la primera pantalla.

**Problemas encontrados**

- Falsos positivos de mi QA (no del código): (a) texto interpolado en SSR aparece con `<!-- -->` entre fragmentos,
  por lo que no se usa en `--expect` del check de ruta; (b) el logo de móvil oculto en escritorio (`display:none`,
  `loading=lazy`) contaba como “imagen rota”; ahora solo se cuentan imágenes visibles.
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
