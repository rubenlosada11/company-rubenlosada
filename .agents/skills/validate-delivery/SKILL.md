---
name: validate-delivery
description: Valida que los cambios del monorepo TrackFlow están listos para entregarse (lint, typecheck, tests, build, arranque de las apps, rutas y cambios accidentales) antes de hacer un commit. Úsala siempre antes de `git commit`.
---

# validate-delivery

## Objective

**Validar que los cambios del monorepo están preparados para entrega antes de realizar un commit**, ejecutando
comprobaciones reales sobre las apps/paquetes afectados y devolviendo un veredicto explícito: *listo* o *no listo*.

Esta skill **solo valida**: no arregla código, no hace commit y no modifica ficheros de la aplicación.

## Inputs

| Input | Cómo obtenerlo |
| --- | --- |
| Ficheros modificados | `git status --porcelain -uall` y `git diff --name-only` (+ `--staged`) |
| Rama actual | `git branch --show-current` (no debe ser `main`) |
| Apps/paquetes afectados | Primer/segundo segmento de cada ruta: `uis/<app>`, `packages/<pkg>`; el resto (`memory-bank/`, `.agents/`, `docs/`, `AGENTS.md`, READMEs) es documentación |
| Package manager | **npm** (un `package-lock.json` por proyecto; no hay workspace raíz) |
| Scripts disponibles | Sección `scripts` de `<app>/package.json` (usa solo los que existan) |
| Puerto de cada app | `uis/website` → 3001, `uis/backoffice` → 3002, `uis/talent-pipeline-tracker` → 3000 |
| Contenido esperado en `/` | `website`: `TrackFlow` y `Solicitar información`; `backoffice`: `Backoffice` y `Áreas de negocio` |

## Procedure

Ejecuta los pasos en orden. Ante el primer fallo, **detente**, informa y no continúes al commit.

1. **Identificar el alcance.**
   `git status --porcelain -uall` → lista de ficheros → apps afectadas. Si solo hay documentación, salta a los
   pasos 6 y 7.

2. **Instalar dependencias si faltan** (solo en apps afectadas): si no existe `node_modules/`, ejecuta
   `npm ci` en la carpeta de la app (usa `npm install` únicamente si no hay `package-lock.json`).

3. **Validaciones estáticas** — desde `uis/<app>` (o `packages/<pkg>`), por este orden:
   ```bash
   npm run lint
   npm run typecheck   # solo si el script existe (website, backoffice, packages/shared)
   npm test            # solo si el script existe (hoy no hay tests en el repo)
   ```

4. **Build de producción** de cada app afectada:
   ```bash
   npm run build
   ```

5. **Arranque y rutas.** Para cada app web afectada, *tras el build*, arranca el servidor de producción en segundo
   plano y comprueba `/`:
   ```bash
   # terminal A (segundo plano) — desde uis/<app>
   npm run start
   # terminal B — desde la raíz del repo
   node .agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3001/ \
     --expect "TrackFlow" --expect "Solicitar información"           # website
   node .agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/ \
     --expect "Backoffice" --expect "Áreas de negocio"               # backoffice
   ```
   Revisa también la salida del servidor: no debe contener `Error`/`⨯`/`unhandled`. **Detén el servidor** al
   terminar (no dejes procesos en segundo plano). Si añadiste rutas nuevas, comprueba también cada una.

6. **Cambios accidentales.** Desde la raíz, indicando los prefijos que forman el alcance de la tarea:
   ```bash
   node .agents/skills/validate-delivery/scripts/check-hygiene.mjs --allow uis/website --allow memory-bank
   ```
   Luego revisa a mano `git diff --stat`.

7. **Memory bank.** Si hubo cambios funcionales, de stack, de comandos o de decisiones: `git diff --name-only`
   debe incluir `memory-bank/progress.md` (y `memory-bank/techContext.md` si hubo decisión técnica). Si no, la
   skill devuelve *no listo*.

## Outputs

Devuelve un informe con esta forma (rellenado con resultados **reales**, nunca supuestos):

```text
## validate-delivery — <rama> — <fecha>
Alcance: <apps/paquetes afectados> | <n> ficheros

| Comprobación                 | Resultado | Evidencia (comando → salida clave)    |
| ---------------------------- | --------- | ------------------------------------- |
| lint <app>                   | ✅/❌/➖    | npm run lint → 0 errores              |
| typecheck <app>              | ✅/❌/➖    | npm run typecheck → 0 errores         |
| tests <app>                  | ✅/❌/➖    | (➖ = no existen)                      |
| build <app>                  | ✅/❌      | npm run build → Compiled successfully |
| arranque + GET / <app>       | ✅/❌      | check-route → OK 200 …                |
| cambios accidentales         | ✅/❌      | check-hygiene → OK                    |
| memory bank actualizado      | ✅/❌/➖    | progress.md en el diff                |

Errores encontrados: <lista con fichero:línea o "ninguno">
Acciones necesarias: <lista o "ninguna">
Estado final: LISTO PARA COMMIT | NO LISTO
```

`➖` solo es válido cuando el script/recurso **no existe**; si existe y no se ejecutó, es ❌.

## Acceptance criteria

La skill devuelve **LISTO PARA COMMIT** si y solo si se cumplen **todos** los criterios aplicables al alcance:

| # | Criterio | Cómo se comprueba | Éxito |
| --- | --- | --- | --- |
| 1 | Lint | `npm run lint` en cada app afectada | código de salida 0, sin errores |
| 2 | Typecheck | `npm run typecheck` (si existe el script) | código de salida 0 |
| 3 | Tests | `npm test` (si existe el script) | código de salida 0 |
| 4 | Build | `npm run build` | código de salida 0 |
| 5 | `website` arranca | `npm run start` + `check-route.mjs http://localhost:3001/ --expect "TrackFlow"` | salida `OK`, código 0 |
| 6 | `backoffice` arranca | `npm run start` + `check-route.mjs http://localhost:3002/ --expect "Backoffice"` | salida `OK`, código 0 |
| 7 | Ruta `/` accesible | `check-route.mjs` | HTTP 200, `text/html`, texto esperado presente, sin textos de error de Next.js |
| 8 | Sin errores de servidor | salida de `npm run start` durante los checks | sin `Error`, `⨯` ni `unhandled` |
| 9 | Sin cambios accidentales | `check-hygiene.mjs --allow <alcance>` | código de salida 0 |
| 10 | Rama correcta | `git branch --show-current` | distinta de `main` |
| 11 | Memory bank al día | `git diff --name-only` (+ `--staged`) | incluye `memory-bank/progress.md` si hay cambios funcionales |

Los criterios 5–8 se aplican solo a `website`/`backoffice` (o cualquier app web nueva con su propio puerto).
Los criterios 1–4 se aplican solo a las apps/paquetes que tengan ese script.
