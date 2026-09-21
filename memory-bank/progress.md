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
| `uis/website` | ⏳ Pendiente |
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

**Problemas encontrados**

- `CONTEXT.md` no existe → se usa `CONTEXT.es.md` (+ `CONTEXT-trackflow.es.md`). Documentado.
- El CONTEXT nombra al CEO de dos formas distintas (Thomas Harry / Daniel Espinoza) → no se muestra en ninguna UI.
- Git sin identidad configurada → se usará identidad por comando, sin tocar la configuración global.

**Problemas resueltos:** los anteriores quedan mitigados (ver decisiones en `techContext.md`).

## Trabajo pendiente

Se completa al cerrar el hito.

## Siguientes pasos

Se completa al cerrar el hito.
