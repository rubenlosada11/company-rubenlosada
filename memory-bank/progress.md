# Progress

> Registro vivo del estado del proyecto. **Actualizar antes de cada commit** en que cambie el estado, una
> decisión o el trabajo pendiente (ver `AGENTS.md`). Añadir entradas nuevas al final de “Historial” (orden
> cronológico); no reescribir el historial anterior.

## Estado actual (resumen)

- **Rama de trabajo:** `feature/propuesta-arquitectura-backend` (desde `main` @ `f11ee15`, que ya incluye las
  PR #3–#6).
- **Hito 4 — Ingeniería impulsada por IA:** entregado y desplegado (PR #3–#6 fusionadas).
- **Propuesta de arquitectura de backend** (entregable del curso, no es un hito numerado): documento
  [`docs/ARCHITECTURE_PROPOSAL.md`](../docs/ARCHITECTURE_PROPOSAL.md) terminado; pendiente de PR y de revisión.
  Solo documentación: **el backend no está implementado**.
- **Última actualización:** 2026-09-25.

| Componente | Estado |
| --- | --- |
| `memory-bank/` | ✅ Creado |
| `AGENTS.md` | ✅ Creado |
| `.agents/rules/project-conventions.md` | ✅ Creado (`scope: always`) |
| `.agents/skills/validate-delivery/` | ✅ Creada (`SKILL.md` + `check-route.mjs` + `check-hygiene.mjs`) |
| `uis/website` | ✅ Implementado, validado y en producción: https://websitetrackflow.rubenlosada.com/ (local `:3001`) |
| `uis/backoffice` | ✅ Implementado, validado y en producción: https://backofficetrackflow.rubenlosada.com/ (local `:3002`; sin autenticación) |
| `services/` | 📝 Propuesta documentada (`docs/ARCHITECTURE_PROPOSAL.md`: `services/api/`, FastAPI); sin código |
| `docs/ARCHITECTURE_PROPOSAL.md` | ✅ Redactado (entregable del curso, no es un hito) |
| PR #3 `feature/agent-memory-bank` → `main` | ✅ Fusionada el 2026-09-21 |
| PR #4 `feature/hito-4-capturas` → `main` | ✅ Fusionada: solo las dos capturas (website y backoffice) |
| PR #5 `feature/hito-4-cierre` → `main` | ✅ Fusionada: Hito 4 “Entregado”, CEO y facturación en el website |
| PR #6 `feature/hito-4-demos-produccion` → `main` | ✅ Fusionada (`f11ee15`): enlaces de producción de website y backoffice |
| PR `feature/propuesta-arquitectura-backend` → `main` | ⏳ Por abrir |

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

- Documentación: `docs/hitos.md` (entrada del Hito 4) y estado del `README.es.md` raíz (ya existe `AGENTS.md`;
  se añaden los Hitos 3 y 4 al bloque de estado).

**Validaciones (commit 4 — verificación final sobre lo commiteado en `b4ba3b6`)**

- Checkout limpio: `git archive` de `uis/website` y `uis/backoffice` → carpeta vacía (sin `node_modules`,
  `.next` ni `next-env.d.ts`) → `npm ci` (exit 0) → `npm run lint` (0) → `npm run typecheck` sin build previo (0)
  → `npm run build` (0), en ambas apps. Demuestra que los lockfiles y el script `typecheck` funcionan en un clon
  nuevo.
- Aviso no bloqueante de npm 11: `npm warn allow-scripts` (scripts de instalación de dependencias no aprobados).
  No afectó a lint, typecheck ni build. No se ha modificado la configuración de npm.

**Problemas encontrados**

- Mi primer arnés de verificación en checkout limpio falló (tubería binaria `git archive | tar` en PowerShell 5.1)
  y ejecutó comandos en la raíz: sin efectos (no hay `package.json` raíz; `git status` intacto). Rehecho con
  `git archive -o` y fail-fast.
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

### 2026-09-22 — Hito 4 (corrección posterior a la PR)

- El desarrollador no pudo arrancar las apps para las capturas: las instrucciones entregadas usaban `&&`, que
  Windows PowerShell 5.1 no admite. Corregidos los READMEs de `website` y `backoffice` y la skill
  `validate-delivery` (un comando por línea, sin `\`), y anotada la restricción en `techContext.md` y `AGENTS.md`.
  Solo documentación; sin cambios de código en las apps. Incluido en la PR #3 (commit `cf11628`).

### 2026-09-22 — cierre del Hito 4 (rama `feature/hito-4-cierre`)

**Contexto:** el desarrollador fusionó la PR #3 (`8152f13`) y añadió las capturas (`uis/website/screenshots/` y
`uis/backoffice/screenshots/`), que se subieron aparte en la PR #4 a petición suya.

**Decisiones del desarrollador**

- **CEO = Thomas Harry** (`CONTEXT.es.md` también cita a Daniel Espinoza; el CONTEXT no se modifica).
- **Facturación anual (~9 M€) se publica en el website** para dar credibilidad ante posibles clientes.
- **No hace falta revisión del copy con Miguel Torres**: es un ejercicio ficticio de bootcamp.
- Sin autenticación en el backoffice: no publicarlo abierto (sin cambios).

**Trabajo realizado**

- Hito 4 pasa a `delivered` en `uis/backoffice/lib/data/milestones.ts` (condición: PR #3 fusionada).
- Backoffice: Dirección ejecutiva muestra “Thomas Harry · Fundador y CEO” (antes sin nombre).
- Website: nueva cifra “~9 M€ · Facturación anual” en la franja de datos del hero (ahora 5 datos; rejilla
  `lg:grid-cols-5`, en 2 columnas el último ocupa el ancho completo; valores alineados arriba con `justify-end`).
- Documentación actualizada: `projectbrief.md`, `project-conventions.md` y los READMEs de ambas apps.

**Validaciones (worktree limpio desde `origin/main`, `npm ci` en ambas apps)**

- `lint`, `typecheck` y `build` de website y backoffice → exit 0.
- `check-route.mjs`: website `/` → OK 200 (3/3 textos, incl. “Facturación anual”); backoffice `/` → OK 200 (3/3,
  incl. “Thomas Harry”).
- Navegador real (Edge headless): 5 datos en la franja; en 1440 px en una sola fila; en 820 y 390 px el 5.º ocupa
  el ancho completo; sin desborde horizontal; CEO visible y sin “Daniel Espinoza”; hitos: 4 “Entregado”, 0 “En
  curso”; filtro del backoffice intacto (33 de 33); 0 errores de consola/red.

**Problemas encontrados y resueltos**

- Con 5 datos, los valores “2” y “8” quedaban desalineados por las etiquetas de dos líneas → corregido con
  `justify-end` en la celda (verificado visualmente).
- La captura del website de la PR #4 se hizo con 4 datos; queda desactualizada respecto a este cierre (ver pendiente).

### 2026-09-22 — demos de producción (rama `feature/hito-4-demos-produccion`)

**Contexto:** el desarrollador publicó ambas apps (un agente del servidor las extrajo desde GitHub) y pidió
registrar las demos “igual que en las demás uis”. Las PR #3, #4 y #5 ya estaban fusionadas.

**Demos de producción (verificadas en vivo el 2026-09-22)**

| App | URL | Verificación |
| --- | --- | --- |
| website | https://websitetrackflow.rubenlosada.com/ | 200; `check-route.mjs` 3/3 (“Facturación anual”, “Solicitar información”, JSON-LD) |
| backoffice | https://backofficetrackflow.rubenlosada.com/ | 200 **sin autenticación**; `check-route.mjs` 3/3 (“Thomas Harry · Fundador y CEO”, “Áreas de negocio”, `noindex`) |

**Trabajo realizado**

- `LINK_PRODUCCION.md` en `uis/website` y `uis/backoffice`, con el mismo formato que las demás uis, y sección
  “Demo pública” en sus READMEs.
- `docs/hitos.md` (Hito 4, ya con demos) y bloque de estado del `README.es.md` raíz.
- Backoffice: la lista de hitos muestra ahora las demos de todos los hitos. El tipo `Milestone` pasa de `demoUrl`
  (una) a `demos` (varias), porque el Hito 4 tiene dos (website y backoffice).
- `techContext.md`: nueva sección “URLs de producción” con el método de despliegue.
- README del backoffice: el aviso “no publicar abierto” pasa a “hoy está publicado abierto; protegerlo antes de
  mostrar datos reales”.

**Validaciones (worktree limpio desde `origin/main`, `npm ci` en backoffice)**

- Backoffice: `lint`, `typecheck` y `build` → exit 0; `check-route.mjs` sobre `/` → OK 200 (4/4 textos).
- Navegador real (Edge headless): Hitos 1–3 con “Demo pública” y su URL, Hito 4 con “Demo website” y “Demo
  backoffice”; 5 enlaces en total, todos con `target=_blank` y `rel=noopener`; 4 hitos “Entregado”; 0 errores de
  consola.
- Website: solo cambian `README.md` y `LINK_PRODUCCION.md` (sin código): no requiere build.
- Ambas producciones comprobadas con `check-route.mjs` antes de enlazarlas.

### 2026-09-25 — Propuesta de arquitectura de backend (rama `feature/propuesta-arquitectura-backend`)

**Objetivo:** entregable “Propuesta de Arquitectura de Backend” (4Geeks). **Solo documentación**: el desarrollador
pidió expresamente no implementar el backend, no instalar dependencias y no tocar los frontends.

**Trabajo realizado**

- Inspección del repo (CONTEXT, memory bank, `packages/shared`, apps de `uis/`, READMEs de carpetas) para basar la
  propuesta en hechos, e investigación de la documentación oficial de FastAPI (Bigger Applications, Dependencies,
  Settings, SQL Databases, Extra Models, Handling Errors, Testing, CORS, Metadata, Security, Background Tasks,
  Full Stack FastAPI Template), MDN (CORS), Next.js (variables de entorno), Twelve-Factor (Config) y Fowler
  (MonolithFirst).
- `docs/ARCHITECTURE_PROPOSAL.md` (commit `d0f9bb6`): **monolito modular por dominios** en `services/api/` (no
  `backend/`, por la convención del `README.es.md`), capas router → servicio → repositorio dentro de cada dominio y
  capa `integrations/` (transportistas, SGA, ERP). Dominios: `commercial`, `last_mile`, `reverse_logistics`,
  `warehouse`, `customer_service`, `reporting`, `identity`. API versionada en `/api/v1`, un `APIRouter` por recurso,
  tracking público en router propio. 6 riesgos con mitigación, trade-offs y evolución por fases.
- Índice de `docs/README.md` y `docs/README.es.md` actualizado.

**Validaciones**

- Solo documentación: lint, typecheck, build y arranque no aplican (ninguna app afectada).
- `check-hygiene.mjs --allow docs` → OK (exit 0). Todos los enlaces relativos del documento apuntan a ficheros
  existentes (comprobado con script).
- Revisión manual contra los 10 requisitos de la rúbrica del hito.

**Supuestos abiertos del documento (requieren confirmación antes de implementar)**

- Base de datos PostgreSQL; `docker-compose.yml` para desarrollo local (área de infraestructura protegida).
- Dominio de producción de la API (DNS de `rubenlosada.com`, área protegida) y existencia de un entorno de staging.
- Mecanismo de autenticación (OAuth2/Bearer con `fastapi.security` o proveedor externo).
- Moneda de las operaciones de EE. UU. (hoy `packages/shared` solo usa EUR) y zona horaria del informe semanal.
- Conectar el formulario de `uis/landing` a `POST /api/v1/leads` exigiría modificar una app de hito anterior.

**Problemas encontrados**

- `progress.md` indicaba la PR de demos de producción como abierta; `git log` muestra que se fusionó como PR #6
  (`f11ee15`). Corregido en el resumen de estado.
- Los commits se etiquetaron primero como “Hito 5”. El desarrollador aclaró que **no es un hito**: faltan varias
  entregas del proyecto antes del Hito 5. Se corrigieron los mensajes antes del push. No añadir esta propuesta a
  `docs/hitos.md`.

## Trabajo pendiente

**Manual del desarrollador (no se puede automatizar ni simular)**

- Abrir y fusionar la PR `feature/propuesta-arquitectura-backend` → `main` (propuesta de arquitectura de backend).
- Opcional: rehacer la captura del website (`uis/website/screenshots/screenshot website.png`), que se hizo con 4
  datos y hoy el hero muestra 5.
- Configurar `user.name`/`user.email` de Git en la máquina (los commits usan la identidad `noreply` de GitHub
  pasada por `-c`, sin tocar la configuración).
- Tras fusionar, actualizar la rama local: `git checkout main` y `git pull`.

**Decisiones abiertas (requieren confirmación; ver `projectbrief.md`)**

- Supuestos de `docs/ARCHITECTURE_PROPOSAL.md` (base de datos, dominio de la API, staging, autenticación, moneda):
  validarlos antes de crear `services/api/`.

**Deuda técnica conocida**

- Sin tests automatizados ni CI en todo el repo; las validaciones dependen del flujo de `AGENTS.md` y de la skill.
- Backoffice publicado **sin autenticación** (`noindex`; los datos son ficticios). Protegerlo (Basic Auth en el
  proxy o login en la app) antes de mostrar datos reales.
- Logo, favicon e imagen duplicados por app (patrón ya usado por el tracker). Si crece, valorar `packages/`
  (requiere confirmación).
- El `README.es.md` raíz sigue nombrando `CONTEXT.md` en varios sitios (plantilla); el fichero real es
  `CONTEXT.es.md`.
- Sin workspace raíz: cada app se instala y valida por separado.

## Siguientes pasos

1. Abrir y fusionar la PR de la propuesta de arquitectura de backend.
2. Validar con el desarrollador los supuestos del documento y, tras su aprobación, crear el esqueleto de la fase 1
   en `services/api/` (core, `/health`, `commercial`, `last_mile`, `reverse_logistics`), según
   `docs/ARCHITECTURE_PROPOSAL.md` §15.
3. Siguientes hitos del curso (README raíz: Telemetría, RAG, Agentes, Workflows, Tiempo real): cada uno debe
   arrancar leyendo este memory bank y cerrar actualizando `progress.md`.
4. Conectar el backoffice a la API **solo después** de añadir autenticación (riesgo R5 del documento) y sustituir
   los “datos de partida” estáticos de `lib/data/`.
5. Valorar añadir un runner de tests y CI (requiere confirmación) y automatizar `validate-delivery` en CI.
