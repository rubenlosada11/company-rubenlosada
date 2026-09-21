---
name: project-conventions
description: Convenciones obligatorias del monorepo TrackFlow para cualquier agente de programación.
scope: always
---

# Project conventions (scope: always)

Aplica a **todas** las tareas, en cualquier carpeta del repo. Protocolo completo en [`AGENTS.md`](../../AGENTS.md).

## 1. Leer antes de tocar código

- [ ] `CONTEXT.es.md` (no existe `CONTEXT.md`; no lo crees) y, si la tarea es de web/hitos,
      `CONTEXT-trackflow.es.md`.
- [ ] `memory-bank/projectbrief.md`, `memory-bank/techContext.md`, `memory-bank/progress.md`.
- [ ] El `README.md` de la carpeta donde vas a trabajar.

## 2. No inventar información de negocio

- Usa **solo** datos presentes en `CONTEXT*.es.md` o en el repo.
- Prohibido inventar: clientes, logos, cifras, métricas, certificaciones, premios, precios, plazos, nombres de
  personas o de transportistas, tecnologías internas.
- Si falta un dato: usa contenido estructurado no numérico o **pregunta**.
- El CEO es **Thomas Harry** (decisión del desarrollador, 2026-09-22). `CONTEXT.es.md` también cita a Daniel Espinoza:
  no lo uses ni edites el CONTEXT sin confirmación (ver `projectbrief.md`).

## 3. Respetar la estructura del monorepo

- Interfaz visual → `uis/`; API/segundo plano → `services/`; código compartido por 2+ carpetas → `packages/`.
- No muevas ni renombres carpetas de primer nivel. No añadas `package.json`/workspace en la raíz.
- Cada app nueva: subcarpeta + `README.md` + entrada en `uis/README.md` y `uis/README.es.md`.

## 4. Evitar duplicación

- Antes de crear un componente, util, formulario o carpeta: busca (`Glob`/`Grep`) si ya existe algo equivalente.
- El formulario de captación de leads ya existe en `uis/landing/formulario/`: enlázalo, no lo reimplementes.
- No copies bloques de código entre apps sin plantearte si es `packages/`… y pregunta antes de extraerlo.

## 5. Mantener separados `uis/website` y `uis/backoffice`

- Proyectos independientes: `package.json`, lockfile, layout, estilos y datos propios.
- Prohibido `import` entre ambos y rutas relativas que salgan de la carpeta de la app (`../../website/...`).
- Website = público, orientado a marcas de e-commerce. Backoffice = interno, orientado a equipos de TrackFlow.

## 6. Actualizar el memory bank

- Al terminar cualquier avance o decisión: editar `memory-bank/progress.md` (estado, validaciones, pendientes).
- Si cambia el stack, un comando, un puerto o una decisión técnica: editar también `memory-bank/techContext.md`.
- Nunca dejes el memory bank contradiciendo el código.

## 7. Validar antes de commit

Por cada app/paquete afectado, desde su carpeta y por este orden: `npm run lint` → `npm run typecheck`
(si existe) → tests (si existen) → `npm run build` → arrancar y comprobar `/`. Usa la skill
[`validate-delivery`](../skills/validate-delivery/SKILL.md). Sin validación verde no hay commit. Nunca reportes
como ejecutado algo que no ejecutaste.

## 8. Detenerse y pedir confirmación

Para cualquiera de estos casos, **para y pregunta** antes de actuar: `CONTEXT*.es.md`, `.env*`/secretos/
credenciales, `infra/`/Docker/dominios, `.github/` y CI/CD, apps de hitos anteriores, `packages/shared`,
migraciones o borrados de datos, cambios de arquitectura o de framework, subidas de versión mayor o dependencias
nuevas sin justificar, operaciones git destructivas (`reset --hard`, `clean -fd`, `push --force`), push a `main`
y cualquier fichero fuera del alcance de la tarea.

## Estilo de código (resumen operativo)

- TypeScript estricto, sin `any` salvo justificación; componentes de servidor por defecto, `"use client"` solo si
  hay estado/eventos.
- Tailwind con las convenciones del repo (Archivo/Manrope, `blue-700`, contenedor `w-[min(1120px,92vw)]`).
- Textos de UI en español, accesibles (landmarks, `alt`, foco visible, contraste).
- Commits en español, `Hito N — descripción`, solo con los ficheros del alcance.
