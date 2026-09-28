# Progress

> Registro vivo del estado del proyecto. **Actualizar antes de cada commit** en que cambie el estado, una
> decisión o el trabajo pendiente (ver `AGENTS.md`). Añadir entradas nuevas al final de “Historial” (orden
> cronológico); no reescribir el historial anterior.

## Estado actual (resumen)

- **Rama de trabajo:** `feature/analizador-incidencias` (desde `main` @ `40ec659`, que ya incluye las PR #3–#8).
- **Hito 4 — Ingeniería impulsada por IA:** entregado y desplegado (PR #3–#6 fusionadas).
- **Propuesta de arquitectura de backend** (entregable del curso, no es un hito numerado): PR #7 fusionada.
- **Directorio de proveedores** (práctica sin número de hito; contexto en
  [`CONTEXT-directorio.md`](../CONTEXT-directorio.md)): entregado, PR #8 fusionada (`40ec659`). API solo local.
- **Analizador de incidencias** (práctica sin número de hito; contexto en
  [`CONTEXT-incidencias.es.md`](../CONTEXT-incidencias.es.md)): **en curso**. Se integra en el monorepo desde el
  repositorio `analizador-incidencias` (construido allí por error; solo lectura), por fases con confirmación.
- **Última actualización:** 2026-09-28.

| Componente | Estado |
| --- | --- |
| `memory-bank/` | ✅ Creado |
| `AGENTS.md` | ✅ Creado |
| `.agents/rules/project-conventions.md` | ✅ Creado (`scope: always`) |
| `.agents/skills/validate-delivery/` | ✅ Creada (`SKILL.md` + `check-route.mjs` + `check-hygiene.mjs`) |
| `uis/website` | ✅ Implementado, validado y en producción: https://websitetrackflow.rubenlosada.com/ (local `:3001`) |
| `uis/backoffice` | ✅ Implementado, validado y en producción: https://backofficetrackflow.rubenlosada.com/ (local `:3002`; sin autenticación) |
| `services/api/` | ✅ Directorio de proveedores: API completa (6 endpoints) + seeder, 118 tests OK; solo local |
| `uis/backoffice/proveedores` | ✅ Implementado y validado en local (E2E 47/47); en producción muestra el aviso de API no configurada |
| Analizador de incidencias | 🚧 Fase 4 de 8: CONTEXT, paquete, script (70 tests) y endpoints `/api/incidents` en `services/api` (144 tests) |
| `docs/ARCHITECTURE_PROPOSAL.md` | ✅ Redactado (entregable del curso, no es un hito) |
| PR #3 `feature/agent-memory-bank` → `main` | ✅ Fusionada el 2026-09-21 |
| PR #4 `feature/hito-4-capturas` → `main` | ✅ Fusionada: solo las dos capturas (website y backoffice) |
| PR #5 `feature/hito-4-cierre` → `main` | ✅ Fusionada: Hito 4 “Entregado”, CEO y facturación en el website |
| PR #6 `feature/hito-4-demos-produccion` → `main` | ✅ Fusionada (`f11ee15`): enlaces de producción de website y backoffice |
| PR #7 `feature/propuesta-arquitectura-backend` → `main` | ✅ Fusionada (`ee34a08`) |
| PR #8 `feature/supplier-directory` → `main` | ✅ Fusionada (`40ec659`) |

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

### 2026-09-27/28 — Directorio de proveedores (rama `feature/supplier-directory`)

**Objetivo:** directorio centralizado de proveedores (Carlos Vega / Ana Whitfield) con FastAPI + Pydantic + TinyDB
en `services/api/` y una página en `uis/backoffice`. Fuente de verdad: `CONTEXT-directorio.md` (10 campos,
8 categorías, 2 estados, 15 proveedores de seed, moneda por país). Se trabaja por fases con parada y confirmación.

**Decisiones del desarrollador (2026-09-27)**

- Crear `services/api/` con paquete `app/` (entrypoint `app.main:app`), **TinyDB como excepción deliberada** a la
  propuesta de `docs/ARCHITECTURE_PROPOSAL.md` (PostgreSQL/SQLAlchemy); sin Docker ni ORM.
- `DELETE /suppliers/{id}` solo en la API: **sin botón de eliminar en la UI** (el CONTEXT dice “suspender, no
  eliminar”).
- Clave natural del seeder: `(name, country)`; `POST` no rechaza duplicados (el CONTEXT no lo pide).
- `contact_email`: validación básica por regex, sin dependencia `email-validator`.
- Se autoriza `uis/backoffice/.env.example` (`NEXT_PUBLIC_API_BASE_URL`); la API es **solo local** por ahora.
- `CONTEXT-directorio.md` se versiona. Commits: `Directorio de proveedores — <cambio concreto>` (no hay hito aún).

**Commit 1 — entorno `uv` y modelos Pydantic**

- `services/api/pyproject.toml` (backend `uv_build`, `module-root = ""`), `uv.lock`, `.gitignore`, `app/main.py`
  (`GET /health`), `app/models.py`, `tests/test_models.py`.
- Modelos: `StrEnum` `Country`/`Currency`/`Category`/`Status` con los valores exactos del CONTEXT; `SupplierCreate`
  (tarifa `> 0`, finita y `strict`, categorías ≥ 1 sin duplicados, moneda coherente con el país, email básico,
  opcionales vacíos → `None`; `id`/`updated_at` enviados por el cliente se ignoran), `SupplierRateUpdate`,
  `SupplierStatusUpdate`, `Supplier` (respuesta con `id` y `updated_at`), `utc_now()`.
- Validaciones: `uv run pytest -q` → 38 passed (también con `-W error::DeprecationWarning`). Los 15 proveedores del
  CONTEXT validan sin alteraciones. App FastAPI temporal: válido → 201; status inválido, tarifa 0/negativa, sin
  `name`, USA+EUR → 422. `uv run uvicorn app.main:app` → `/health` 200, `/docs` 200.

**Problemas encontrados y resueltos**

- En modo laxo Pydantic aceptaba `true` como tarifa (`1.0`) y `"7.45"` como texto → campo `strict=True`.
- Starlette 1.7 marca como obsoleto `TestClient` con `httpx` → dependencia de desarrollo cambiada a `httpx2`.
- `git config` local tiene ahora un email personal; se mantiene la identidad `noreply` de GitHub pasada por `-c`.
- `check-route.mjs` exige `text/html`: da FAIL con endpoints JSON aunque respondan 200. Para la API se usa `curl`.

**Commit 2 — persistencia TinyDB**

- `app/database.py`: `suppliers_table()` (context manager) y `get_suppliers_table()` (dependencia de FastAPI).
  Fichero `services/api/db/suppliers.json` (ignorado en git; `git check-ignore` lo confirma), configurable con
  `SUPPLIERS_DB_PATH`; UTF-8 legible (`ensure_ascii=False`, `indent=2`). Se abre y cierra en cada uso (lee siempre
  el disco, también si el seeder escribe con la API arrancada) y un `threading.Lock` serializa el acceso.
- `tests/conftest.py` (fixture `db_path` temporal) y `tests/test_database.py` (7 tests: ruta, ids, UTF-8,
  reapertura, lectura desde otro proceso, 40 escrituras concurrentes).
- Validaciones: `uv run pytest -q` → 45 passed; `db/` real sin tocar. Prueba negativa: sin el candado, 5/5
  intentos con 8 hilos corrompen el JSON (`JSONDecodeError`); con candado 0/5. Reinicio real con uvicorn (envoltorio
  temporal fuera del repo con rutas de prueba): arranque 1 (PID 27692) inserta `Nacex` → parada (puerto libre,
  `curl` 000) → arranque 2 (PID 15444) devuelve el mismo registro con `doc_id` 1. Logs sin errores.
- La consola de Python en Windows usa cp1252 (los acentos se ven mal al imprimir); el fichero está bien en UTF-8.
  Tenerlo en cuenta en la salida del seeder.

**Commit 3 — seeder**

- `app/seed.py`: `SUPPLIERS_SEED` copiado literalmente del CONTEXT (15), validado con `SupplierCreate`, `updated_at`
  del servidor; idempotente por `(name casefold, country)`; no modifica existentes. Salida `Seeder completed.` /
  `Inserted` / `Skipped` / `Total` + lista `+`/`=` por proveedor. `pyproject.toml`: `[project.scripts] seed`.
- `tests/test_seed.py` (9 tests): seed idéntico al bloque del CONTEXT (leído con `ast`), 1.ª ejecución 15/0/15,
  2.ª 0/15/15 con los mismos ids, solo inserta los que faltan, no pisa cambios, mayúsculas, mismo nombre en otro país,
  salida real de `main()`.
- Validaciones: `uv run pytest -q` → 54 passed. `uv run seed` real en PowerShell sobre `db/` vacío → Inserted 15,
  Skipped 0, Total 15; 2.ª ejecución → 0 / 15 / 15; exit 0 ambas; acentos correctos. Comprobación independiente del
  fichero: 15 registros (ids 1–15), 15 claves únicas, idéntico al CONTEXT, todos con `updated_at` UTC; 13 activos
  (suspendidos: Laser Ship, SAP WM Cloud); 9 USA / 6 Spain.
- Limitación documentada: el candado no cubre otros procesos → ejecutar el seeder con la API parada o sin ediciones.

**Commit 4 — API de proveedores y tests**

- `app/routes/suppliers.py`: `POST` (201), `GET` con filtros `country`/`category` (enums → 422 si no existen;
  `category` = pertenece a `categories`; combinables con AND), `GET /{id}`, `PATCH /{id}/rate` (renueva
  `updated_at`), `PATCH /{id}/status` (no toca `updated_at`), `DELETE /{id}` (204). 404 con
  `"Proveedor {id} no encontrado"`. Acceso a TinyDB por la dependencia `get_suppliers_table`; helpers `to_supplier`
  y `get_or_404`. `app/main.py`: router + CORS (`CORS_ALLOWED_ORIGINS`, por defecto `localhost:3002` y
  `127.0.0.1:3002`; métodos GET/POST/PATCH/DELETE; cabecera `Content-Type`).
- `tests/test_api.py` + fixtures `client`/`seeded_client`: POST (201, id, timestamp, ignora id/updated_at del cliente,
  422 por cada regla, campos obligatorios), GET (todos, país, categoría, multicategoría, combinado, 422 de filtros,
  404, id no numérico), PATCH tarifa (valor, `updated_at` más reciente y persistido, 0/negativo/texto/bool/null →
  422 sin cambios, 404), PATCH estado (válido, no toca `updated_at`, inválidos → 422, 404), DELETE (204 y 404),
  persistencia en otro proceso, CORS.
- Validaciones: `uv run pytest -q -W error::DeprecationWarning` → 116 passed. Mutaciones (quitar `updated_at` del
  PATCH, ignorar el filtro de categoría, quitar el 404) → 1, 7 y 7 tests fallan; restaurado → 116 passed.
  HTTP real con uvicorn sobre una copia de la base: filtros (Spain 6, reverse_logistics 2, Spain+carrier_last_mile
  4, carrier_international 2), POST 201 / 422 (8 casos), PATCH tarifa 7.45→7.99 con `updated_at` nuevo, PATCH
  estado, DELETE 204→404, reinicio del servidor conserva la tarifa, preflight CORS OK solo para `:3002`. Logs sin
  errores ni 500. La base real `db/` sigue intacta (15, UPS 7.45).

**Problemas encontrados**

- `curl` con el JSON como argumento en Windows envía los acentos en cp1252 → la API responde 400 (cuerpo no UTF-8).
  Es de la herramienta de prueba: con fichero UTF-8 o `urllib` funciona. En la documentación, usar Swagger UI o
  `--data-binary @fichero.json`.
- TinyDB reutiliza el `id` más alto si se borra ese proveedor (siguiente = máximo + 1). Se documenta como limitación:
  el briefing pide que TinyDB asigne el id y la UI no borra.

**Commit 5 — backoffice: página `/proveedores`**

- Ruta `app/proveedores/page.tsx` + componentes cliente `SupplierDirectory` (filtros → `GET /suppliers?…` con
  `AbortController`; “cargando” derivado de la clave de la petición por la regla `react-hooks/set-state-in-effect`),
  `SupplierForm` (alta, validación en cliente, moneda derivada del país, errores 422 de FastAPI por campo) y
  `SupplierRow` (tarifa editable en la fila y suspender/reactivar, con carga y error por fila; badges emerald/ámbar).
  `lib/http.ts` (patrón del tracker; `ApiError.fieldErrors`), `lib/suppliers.ts`, `lib/data/suppliers.ts` (enums del
  CONTEXT + etiquetas en español), tipos `Supplier*` en `types/index.ts`, `.env.example`
  (`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`). Sin botón de eliminar.
- Menú: `lib/nav.ts` pasa a `/#resumen`… + `/proveedores`; `NavLink` (cliente) marca `aria-current` y en móvil
  desplaza el chip activo a la vista (`scroll-px-*` en el `nav`). Pie del sidebar actualizado.
- Si falta `NEXT_PUBLIC_API_BASE_URL` **no se lanza al importar** (rompería `next build` en producción): la página
  muestra un aviso. Build sin la variable → OK y aviso visible (simula la demo pública).
- Validaciones: `npm ci` (aviso `allow-scripts` ya conocido), `lint` 0, `typecheck` 0, `build` 0 (con y sin la
  variable). `check-route`: `/` 200 (3/3, incl. Thomas Harry) y `/proveedores` 200. E2E Edge headless
  (playwright-core fuera del repo, API sobre una copia de la base): **47/47** — menú y `aria-current`, 15 filas,
  filtros país/categoría/combinado/vacío con la petición exacta y 0 navegaciones, alta (4 errores de cliente sin
  petición, email, 422 real de FastAPI mostrado en alerta y en el campo, 201 id 16, cuerpo sin `id`/`updated_at`,
  guardado en TinyDB), tarifa (0 en cliente sin PATCH, “Guardando…”, 7,99 al momento, `updated_at` renovado en
  TinyDB y en la fila, error 422 en la fila), estado (badges, TinyDB, `updated_at` intacto, contador), sin botón de
  borrar, 390 px sin desborde, API caída → aviso + Reintentar, 0 errores de consola. Regresión de `/`: anclas desde
  `/proveedores`, filtro de iniciativas 33/33. Logs de API y backoffice sin errores ni 500. Base real intacta.

**Problemas encontrados y resueltos**

- Clases de color activas e inactivas a la vez (`bg-white` + `bg-blue-700`) dependían del orden del CSS → `NavLink`
  separa `inactiveClassName`/`activeClassName`.
- En móvil el chip “Proveedores” quedaba fuera de la vista → `scrollIntoView` + `scroll-padding`; comprobado a 390 px.
- Fallos de selectores de mis scripts E2E (`role=alert` del anunciador de rutas de Next, `aria-label="Categorías"`
  de las filas), no de la app.

**Commit 6 — revisión de entrega, seguridad y documentación**

- Checkout limpio de `5c817cc` (`git archive`, sin `.venv`/`node_modules`/`.next`/`db`): `uv sync --locked`, 116
  passed, `uv run seed` 15/0/15 y 0/15/15; backoffice `npm ci` (0 vulnerabilidades), lint, typecheck y build → 0.
- Seguridad (`main...HEAD`, 33 ficheros): sin `.env` (solo los dos `.env.example`), ni base de datos, `.venv`,
  `node_modules`, `.next`, logs ni claves versionados; patrones de secretos → solo falsos positivos (`reloadToken`);
  URLs del código solo locales (+ `evil.example` en un test de CORS). La API no tiene autenticación: documentado
  como solo local.
- **Corrección:** FastAPI respondía `application/json` sin `charset` y Windows PowerShell 5.1 (`Invoke-RestMethod`)
  mostraba “MRW EspaÃ±a”. `app/main.py`: `default_response_class` con `application/json; charset=utf-8`; 2 tests
  nuevos (118). Comprobado en PowerShell 5.1: acentos correctos.
- Documentación: `services/api/README.md` completo (instalación, ejecución, variables, seeder, modelo, 6 endpoints
  con respuestas **reales** capturadas de la API, comandos PowerShell 5.1 verificados, tests, persistencia,
  limitaciones); `services/README*.md` (tabla de servicios); `uis/README*.md` (backoffice + `/proveedores`);
  `AGENTS.md` y skill `validate-delivery` (ya hay `services/api` y tests con pytest; `check-route` solo HTML).
- Mi script de edición convirtió `\a` de `services\api` en un carácter de control en `AGENTS.md`: detectado en el diff
  y corregido (0 ficheros de texto versionados con `\x07`).
- PowerShell 5.1: `Invoke-RestMethod` con una lista JSON necesita paréntesis para enumerarla; documentado.
- Capturas del desarrollador (revisadas: contenido correcto y sin datos sensibles), enlazadas desde los READMEs:
  `services/api/screenshots/screenshot seeder.png` (15/0/15 y 0/15/15), `screenshot endpoint filtro pais1-3.png`
  (Swagger, `?country=Spain`, 200, `charset=utf-8`) y `uis/backoffice/screenshots/screenshot proveedores
  filtro1-2.png` (España + última milla → 4; España → 6).
- Commit 6 + push de `feature/supplier-directory` + PR a `main` (ver estado).

### 2026-09-28 — Analizador de incidencias (rama `feature/analizador-incidencias`)

**Objetivo:** traer al monorepo el analizador del CSV de incidencias de CX (Valentina Cruz), que se construyó, probó
y fusionó por error en el repositorio `analizador-incidencias` (PR #1). Se adapta a las convenciones del monorepo, sin
reconstruirlo ni copiarlo a ciegas. Ese repositorio es **solo lectura**; qué hacer con él se decide al final.
Piezas: paquete Python compartido `packages/analisis-incidencias`, CLI `scripts/analyze.py`, endpoints en
`services/api` y página `/incidencias` en el backoffice. Fases con parada y confirmación antes de cada commit.

**Fase 0 — auditoría (sin cambios)**

- `main` @ `40ec659` al día con `origin/main`. Base: `services/api` `uv lock --check` OK y 118 passed; backoffice
  `lint`/`typecheck`/`build` → 0. El script de la fuente reproduce los valores esperados del CONTEXT (100/95/5).
- Choques detectados: `app/main.py` sin `create_app` y con `/health` (no `/api/health`), CORS sin `expose_headers`,
  sin configuración de logging; `lib/http.ts` fuerza `Content-Type: application/json` y lee siempre JSON (rompe
  `FormData` y la descarga del CSV). `StatCard` y `PageSection` son idénticos en ambos repos (se reutilizan).

**Decisiones del desarrollador (2026-09-28)**

- **D1:** `CONTEXT-incidencias.es.md` en la raíz, copia literal del `CONTEXT.es.md` de la fuente. El `CONTEXT.es.md`
  de la empresa no se toca.
- **D2:** capturas **manuales** del desarrollador (no se reutilizan las generadas de la fuente); se preparan el
  entorno, los nombres y las carpetas `screenshots/` en la fase de documentación.
- **D3:** pruebas en navegador fuera del repo (Edge + `playwright-core` en el scratchpad), sin dependencia nueva en
  el backoffice.
- **D4:** errores inesperados capturados solo en el router de incidencias (log + 500 `{"detail": "Error interno del
  servidor."}`); logger `trackflow` a INFO en `main.py` sin tocar el logger raíz.
- **D5:** CORS con `expose_headers=["Content-Disposition"]` para que la descarga conserve el nombre del fichero.
- **D6:** práctica **sin número de hito**: commits `Analizador de incidencias — …`; **no** se añade a
  `docs/hitos.md` ni a `lib/data/milestones.ts` (igual que proveedores). El rastro queda en commits, memory bank,
  READMEs y `docs/`.

**Fase 1 — rama y CONTEXT**

- Rama `feature/analizador-incidencias` desde `main` @ `40ec659`.
- `CONTEXT-incidencias.es.md` = copia literal (`cmp` sin diferencias). Contiene inconsistencias propias ya conocidas
  (menciona 1.000 filas y la ruta `incidents-analysis/…`; la salida esperada está en inglés): mandan la tabla de
  valores esperados (100 filas) y la decisión de salida en español.
- Corregido el estado de este fichero: la PR #8 (proveedores) ya estaba fusionada.
- Commit `9e032ad`.

**Fase 2 — paquete compartido `packages/analisis-incidencias`**

- Copiado desde `HEAD` de la fuente con `git archive` (sin `__pycache__`). Único cambio: las referencias a
  `CONTEXT.es.md` (en el monorepo es el de la empresa) pasan a `CONTEXT-incidencias.es.md` en el README, `dominio.py`
  y `validacion.py` (4 líneas; el resto es idéntico a la fuente).
- `packages/README.md` y `README.es.md`: nueva tabla de paquetes (`shared` y `analisis-incidencias`, con quién los usa).
- `.gitignore` raíz: `__pycache__/`, `*.py[cod]`, `.pytest_cache/` y `scripts/results.csv` (antes solo
  `node_modules/`). Comprobado con `git check-ignore` y `git ls-files --others --ignored`.
- Validación: `python -m pytest packages/analisis-incidencias/tests -q` (desde la raíz) → **43 passed**.
- Commit `0d7c973`.

**Fase 3 — script `scripts/analyze.py`**

- Copiados de la fuente `analyze.py` y `incidents-trackflow.csv` (idénticos) y `tests/test_analyze.py` (solo cambia
  la referencia al CONTEXT). La ruta al paquete (`parents[1] / "packages" / "analisis-incidencias" / "src"`) sigue
  siendo válida. El CSV de prueba se versiona: son datos ficticios del ejercicio.
- `scripts/README.es.md` (uso en PowerShell, pregunta de exportación, códigos de salida, privacidad, tests) y
  `scripts/README.md` (resumen en inglés).
- Validación:
  - `python -m pytest scripts/tests packages/analisis-incidencias/tests -q` → **70 passed**.
  - `python analyze.py incidents-trackflow.csv` desde `scripts/`: 100 · 95 · 5; inválidos TRF-000003 (seguimiento),
    TRF-000025 (transportista/país), TRF-000042 (categoría), TRF-000068 (email), TRF-000097 (cerrada sin puntuación);
    categorías 14/38/19/17/7; estados 29/52/14; países 50/45; satisfacción 52 de 52, media 3.06, distribución
    6/11/15/14/6; por país US 2.96 · ES 3.17. Coincide con la sección de valores esperados.
  - Misma salida de consola que el script de la fuente (salvo la ruta de exportación) y `results.csv` **idéntico
    byte a byte** (con BOM UTF-8). Sin `@` en la consola ni en la exportación.
  - Respuesta no válida → repite la pregunta; `s` exporta; `n` y EOF terminan sin exportar (exit 0); fichero
    inexistente → exit 1; sin argumento → exit 2. En Windows PowerShell 5.1: acentos y caracteres de caja correctos,
    exit 0. `scripts/results.csv` borrado tras la prueba (además está ignorado).
- Commit `3fee3b0`.

**Fase 4 — API en el servicio existente (`services/api`)**

- `app/routes/incidents.py` (a partir de `routers/incidents.py` de la fuente): `POST /api/incidents/analyze`
  (multipart, campo `file`) y `GET /api/incidents/results/export`. Errores 400/404/413/415/422; **D4**: los errores
  inesperados se capturan solo en este router (`logger.exception` + 500 `{"detail": "Error interno del servidor."}`),
  también al generar la exportación. Se mantiene el prefijo `/api` del enunciado (proveedores usa `/suppliers`).
- `app/main.py`: registra el router, `app.state.ultimo_analisis = None`, **D5** `expose_headers=["Content-Disposition"]`
  y logger `trackflow` a INFO con su propio handler (formato alineado con uvicorn; el logger raíz no se toca). Sin
  `create_app` ni manejador global: proveedores no cambia.
- `pyproject.toml` con `uv add`: `python-multipart>=0.0.32` y `analisis-incidencias` (`[tool.uv.sources]`, ruta
  `../../packages/analisis-incidencias`, `editable = true`); `uv.lock` regenerado (+18 líneas); `uv lock --check` OK.
- `tests/test_incidents.py`: los 23 de la fuente adaptados (app del módulo, fixture `client` del `conftest.py`, estado
  reiniciado por test con un fixture `autouse`, `/health`, 500 sin `raise_server_exceptions=False`) + 3 nuevos: log
  del análisis sin correos, 500 al exportar y `Access-Control-Expose-Headers`.
- Validación:
  - `uv run pytest -q -W error::DeprecationWarning` → **144 passed** (118 proveedores + 26 incidencias).
  - Mutaciones: sin `expose_headers` falla el test de CORS; sin el `except Exception` falla el test del 500.
    Restaurado → 144 passed.
  - `uv run uvicorn app.main:app --port 8000` + `curl`: `/health` 200; `/suppliers?country=Spain` 200 (6); export sin
    análisis 404; sin fichero 400; `.xlsx` 415; vacío 422; 5 MB + 1 byte 413; CSV de prueba 200
    (`application/json; charset=utf-8`) con todos los valores esperados (100/95/5, inválidos por línea e ID,
    categorías, estados, países, satisfacción 3.06 y 6/11/15/14/6, US 2.96 · ES 3.17) y sin `@`; export 200
    `text/csv; charset=utf-8`, `attachment; filename="results.csv"`, `Access-Control-Expose-Headers:
    Content-Disposition`, **idéntico byte a byte** al `results.csv` del script; un 422 posterior no sustituye el
    último análisis. Preflight CORS: `:3002` permitido, otro origen rechazado; preflight `PATCH /suppliers/1/rate`
    sigue permitido.
  - Log: línea de resumen `trackflow.api.incidents: Análisis de 'incidents-trackflow.csv': 100 registros (95 válidos,
    5 inválidos)`, 0 `@`, 0 errores. Al redirigir el log a un fichero en Windows, las tildes salen en cp1252
    (limitación ya conocida de la fuente; en consola se ven bien).

## Trabajo pendiente

**Manual del desarrollador (no se puede automatizar ni simular)**

- Opcional: rehacer la captura del website (`uis/website/screenshots/screenshot website.png`), que se hizo con 4
  datos y hoy el hero muestra 5.
- Git ya tiene `user.name`/`user.email` en la máquina, pero con un email personal: los commits siguen usando la
  identidad `noreply` de GitHub pasada por `-c`. Si se quiere, cambiar `user.email` a la `noreply`.
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

1. Analizador de incidencias: fases 2–8 (paquete, script, API, página `/incidencias`, documentación y capturas,
   auditoría y PR, instrucciones de despliegue sin ejecutar). Al final, decidir qué hacer con el repositorio
   `analizador-incidencias` (dejarlo o archivarlo en GitHub; no borrarlo).
2. Validar con el desarrollador los supuestos del documento y, tras su aprobación, crear el esqueleto de la fase 1
   en `services/api/` (core, `/health`, `commercial`, `last_mile`, `reverse_logistics`), según
   `docs/ARCHITECTURE_PROPOSAL.md` §15.
3. Siguientes hitos del curso (README raíz: Telemetría, RAG, Agentes, Workflows, Tiempo real): cada uno debe
   arrancar leyendo este memory bank y cerrar actualizando `progress.md`.
4. Conectar el backoffice a la API **solo después** de añadir autenticación (riesgo R5 del documento) y sustituir
   los “datos de partida” estáticos de `lib/data/`.
5. Valorar añadir un runner de tests y CI (requiere confirmación) y automatizar `validate-delivery` en CI.
