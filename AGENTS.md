# AGENTS.md — Protocolo para agentes de programación

Monorepo de **TrackFlow** (logística de última milla y almacenes, EE. UU. + España), proyecto transversal de
4Geeks AI Engineering. Este fichero es el protocolo operativo para cualquier agente (Claude Code, Cursor,
Copilot, etc.). **Léelo entero antes de tocar código.**

## 1. Inicio de sesión (obligatorio)

Antes de modificar **cualquier** fichero, lee en este orden:

1. [`CONTEXT.es.md`](./CONTEXT.es.md) — fuente de verdad del negocio. *(En este repo no existe `CONTEXT.md`; el
   contexto es `CONTEXT.es.md`, con el detalle de hitos en [`CONTEXT-trackflow.es.md`](./CONTEXT-trackflow.es.md).)*
2. [`memory-bank/projectbrief.md`](./memory-bank/projectbrief.md) — qué es la empresa y qué estamos construyendo.
3. [`memory-bank/techContext.md`](./memory-bank/techContext.md) — stack real, comandos, convenciones, decisiones.
4. [`memory-bank/progress.md`](./memory-bank/progress.md) — qué está hecho, qué falta, problemas abiertos.
5. Reglas de [`.agents/rules/`](./.agents/rules/) — hoy: [`project-conventions.md`](./.agents/rules/project-conventions.md)
   (`scope: always`).
6. El `README.md` de la carpeta en la que vas a trabajar (`uis/README.md`, `uis/<app>/README.md`, …).

Después comprueba `git status` y `git branch --show-current`. **No trabajes en `main`**: usa una rama
`feature/<nombre>`.

## 2. Mapa rápido del repositorio

| Necesitas… | Va en |
| --- | --- |
| Interfaz visual pública | `uis/website/` (la `uis/landing/` estática es del Hito 1: no se toca) |
| Interfaz interna / admin | `uis/backoffice/` |
| API o proceso en segundo plano | `services/` (hoy vacío; solo si hace falta de verdad) |
| Tipos/utilidades usados por 2+ carpetas | `packages/` |
| Agente de IA / skill de dominio / MCP | `agents/` / `skills/` / `mcps/` |
| Skill para *agentes de programación* de este repo | `.agents/skills/` |
| Documentación transversal | `docs/` (y `memory-bank/` para contexto de agentes) |

`uis/website` y `uis/backoffice` son **proyectos independientes**: no se importan entre sí.

## 3. Flujo obligatorio antes de cada commit

**No te saltes este proceso, ni siquiera para commits “pequeños” o de documentación.** Si un paso falla, se
corrige y se **reinicia desde el paso 3** (o desde el 1 si el arreglo cambió el diff).

1. **Revisar cambios.** `git status` y `git diff` (más `git diff --staged` si hay algo en el índice). Confirma
   que cada cambio pertenece al alcance de la tarea.
2. **Actualizar el memory bank.** Si cambió una decisión, el stack, un comando o el estado del trabajo, edita
   `memory-bank/progress.md` (siempre que haya avance) y `memory-bank/techContext.md` (si hay decisión técnica).
3. **Ejecutar validaciones** en **cada app/paquete afectado**, desde su carpeta: `npm run lint`,
   `npm run typecheck` (si el script existe), tests (si existen; hoy no hay ninguno) y `npm run build`.
4. **Verificar que las apps arrancan y las rutas funcionan.** Para `website` y `backoffice`: arrancar (`npm run dev`
   o `npm run start` tras el build) y comprobar que `/` responde 200 con su contenido esperado y sin errores en
   la salida del servidor. Usa la skill [`validate-delivery`](./.agents/skills/validate-delivery/SKILL.md), que
   automatiza los pasos 3–5.
5. **Comprobar que no hay cambios accidentales.** `git status` sin ficheros inesperados: nada de `node_modules/`,
   `.next/`, `*.tsbuildinfo`, `.env*` (salvo `.env.example`), logs, capturas temporales ni ficheros fuera del
   alcance. Nada de `AGENTS.md`/`CLAUDE.md` generados dentro de una app.
6. **Commit.** Solo tras superar 1–5. Mensaje claro en español, describiendo el porqué (estilo del historial:
   `Hito N — descripción`). Añade solo los ficheros del alcance (`git add <rutas>`, nunca `git add -A` a ciegas).

Antes de abrir o actualizar una PR repite el flujo y adjunta los resultados reales en la descripción. **Nunca**
declares una validación como pasada si no la has ejecutado.

## 4. Ficheros y áreas que requieren confirmación del desarrollador

**Detente y pregunta** antes de modificar, borrar o crear cualquiera de lo siguiente:

| Área | Por qué |
| --- | --- |
| `CONTEXT.es.md`, `CONTEXT-trackflow.es.md` | Fuente de verdad del negocio. |
| `.env*` (salvo lectura de `.env.example`), secretos, credenciales, tokens, claves | Seguridad. Jamás se commitean. |
| `infra/`, `docker-compose.yml`, Dockerfiles, dominios/DNS (`rubenlosada.com`), configuración de despliegue | Infraestructura. |
| `.github/` (workflows CI/CD), cualquier pipeline de publicación | CI/CD sensible. |
| Apps de hitos anteriores: `uis/landing/`, `uis/script-automatizacion/`, `uis/talent-pipeline-tracker/` | Fuera del alcance del Hito 4; tienen demos públicas. |
| `packages/shared/` (incl. `dist/` versionado) | Lo consumen hitos previos. |
| Migraciones de datos destructivas, borrado o reescritura de `data/raw/` | Pérdida de datos. |
| Cambios arquitectónicos: workspace raíz, mover/renombrar carpetas de primer nivel, crear un backend, compartir código entre `website` y `backoffice`, cambiar de framework | Decisiones de arquitectura. |
| Dependencias: subir versión mayor (Next, React, Tailwind, TypeScript, ESLint), añadir librerías no justificadas, regenerar lockfiles sin motivo | Riesgo de ruptura y ruido. |
| Operaciones git destructivas: `reset --hard`, `clean -fd`, `push --force`, borrar ramas/tags, reescribir historial, push a `main` | Irreversibles. |
| Ficheros fuera del alcance de la tarea actual | Evitar cambios colaterales. |

Ante duda: pregunta. Un “no sé si me dejan” es un “detente”.

## 5. Reglas de trabajo

- **No inventes información de empresa**: clientes, logos, cifras, certificaciones, premios, tecnologías o procesos
  que no estén en `CONTEXT*.es.md` o en el repo. Si falta un dato, usa contenido no numérico o pregunta.
- **Sigue las convenciones existentes** (stack, estilo, estructura). Antes de crear algo, busca si ya existe.
- **Simplicidad**: sin dependencias, capas ni backends “por si acaso”.
- **Idioma**: español para UI, documentación y commits.
- Los `.gitignore` de las apps Next.js ignoran el `AGENTS.md` que `next dev` puede regenerar dentro de la app;
  este `AGENTS.md` (raíz) es el único protocolo vigente.

## 6. Comandos de referencia

Desde la carpeta de la app (`cd uis/<app>`); detalle y puertos en `memory-bank/techContext.md`. El desarrollador
usa **Windows PowerShell 5.1**: no encadenes comandos con `&&` ni `\` al escribirle instrucciones; un comando por
línea.

```bash
npm install          # dependencias (npm + package-lock.json por proyecto)
npm run dev          # desarrollo   — website :3001 · backoffice :3002 · tracker :3000
npm run lint         # eslint
npm run typecheck    # tsc --noEmit (website, backoffice, packages/shared)
npm run build        # compilación de producción
npm run start        # servir el build
```

## 7. Entrega (Git / PR)

- Rama del Hito 4: `feature/agent-memory-bank`. Remoto: `origin` (comprobar con `git remote -v`, no asumir URL).
- Commits pequeños y coherentes; PR hacia `main` con Summary, cambios, validaciones ejecutadas y capturas
  (las capturas las añade el desarrollador a mano: no las generes ni las simules).
- Al terminar una sesión, deja `memory-bank/progress.md` listo para la siguiente.
