# TrackFlow Backoffice

Aplicación interna de TrackFlow Tech. Muestra la estructura del negocio, el backlog de iniciativas de TrackFlow
Tech y el estado de los hitos del proyecto **a partir del contexto de empresa** (ruta `/`), el **directorio de
proveedores** (ruta `/proveedores`) y el **analizador de incidencias** de CX (ruta `/incidencias`), estos dos
conectados a la API [`services/api`](../../services/api/README.md). **Se entra con login** (ruta `/login`): usuario y
contraseña de la API, con un token JWT (ver [Acceso](#acceso-login)).

Next.js (App Router) + React + TypeScript + Tailwind CSS, con las mismas versiones y herramientas que
[`talent-pipeline-tracker`](../talent-pipeline-tracker/README.md). Sin librerías de estado ni de UI.

> Este proyecto es independiente de [`../website`](../website/README.md): layout, estilos y datos propios; no
> comparten código.

## Demo pública

- URL: https://backofficetrackflow.rubenlosada.com/
- La versión publicada es **anterior al login** y lleva `noindex`. **No se debe redesplegar esta versión sin publicar
  antes la API**: el login la necesita y, sin ella, el panel queda inaccesible. Ver
  [`docs/despliegue-api.md`](../../docs/despliegue-api.md).

## Acceso (login)

Pantalla propia en `/login` (no el popup del navegador): panel de marca en escritorio y tarjeta de acceso con
email y contraseña, mostrar/ocultar contraseña, estado «Entrando…» y mensajes de la API en español (credenciales
incorrectas, cuenta desactivada, API caída, sesión caducada, sesión cerrada).

| Pieza | Qué hace |
| --- | --- |
| [`app/login/page.tsx`](./app/login/page.tsx) + [`components/auth/LoginScreen.tsx`](./components/auth/LoginScreen.tsx) | `POST /auth/login` y después `GET /auth/me`. Vuelve a la página de `?next=` (solo rutas internas). |
| [`app/(panel)/layout.tsx`](./app/(panel)/layout.tsx) + [`components/auth/AuthGate.tsx`](./components/auth/AuthGate.tsx) | `/`, `/proveedores` e `/incidencias` solo se muestran con sesión; si no, llevan a `/login?next=…`. Las URLs no cambian (grupo de rutas). |
| [`components/auth/AuthProvider.tsx`](./components/auth/AuthProvider.tsx) | Estado de la sesión compartido. La cierra al caducar el token o si la API responde 401. |
| [`lib/session.ts`](./lib/session.ts) · [`lib/http.ts`](./lib/http.ts) | Token en `sessionStorage` (dura lo que la pestaña, sin cookies) y cabecera `Authorization: Bearer` en cada llamada a la API. |
| [`components/auth/UserMenu.tsx`](./components/auth/UserMenu.tsx) | Barra superior: iniciales, nombre del perfil, rol y **Cerrar sesión**. |

Para entrar hace falta un usuario de la API: el primero se crea con `uv run --env-file .env create-admin <email>` en
`services\api`. Detalle, permisos y verificación: [`docs/autenticacion.md`](../../docs/autenticacion.md). La
comprobación del backoffice es de interfaz: los datos los protege la API, que valida el token en cada petición.

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

## Qué muestra la ruta `/incidencias`

Analizador del CSV de incidencias exportado del helpdesk para Valentina Cruz (CX), según
[`CONTEXT-incidencias.es.md`](../../CONTEXT-incidencias.es.md). Documentación completa:
[`docs/analizador-incidencias.md`](../../docs/analizador-incidencias.md).

| Función | Llamada a la API |
| --- | --- |
| Seleccionar o arrastrar el CSV y analizarlo (“Analizando…” mientras tanto; `.csv` comprobado antes de enviar) | `POST /api/incidents/analyze` (`multipart/form-data`, campo `file`) |
| Resumen, categoría, estado, satisfacción, registros inválidos (por línea e ID, sin correos), más desgloses, evolución temporal y cruces, con números en formato es-ES | — (respuesta del análisis) |
| Botón **Descargar resultados CSV**: `results.csv`, idéntico al que exporta `scripts/analyze.py` | `GET /api/incidents/results/export` |

Los errores de la API (`detail`), una API que no responde o la falta de `NEXT_PUBLIC_API_BASE_URL` se muestran como
aviso en el formulario. Capturas con el CSV de prueba: [resumen](./screenshots/screenshot%20incidencias%20resumen.png),
[registros inválidos](./screenshots/screenshot%20incidencias%20invalidos.png) y
[página completa](./screenshots/screenshot%20incidencias%20completo.png).

## Estructura

```text
backoffice/
├── app/
│   ├── layout.tsx        # fuentes, `noindex` (herramienta interna) y AuthProvider
│   ├── login/page.tsx    # ruta `/login`
│   ├── (panel)/          # grupo de rutas protegido (no cambia las URLs)
│   │   ├── layout.tsx    # AuthGate + sidebar + barra superior
│   │   ├── page.tsx      # ruta `/`
│   │   ├── proveedores/page.tsx  # ruta `/proveedores`
│   │   └── incidencias/page.tsx  # ruta `/incidencias`
│   └── globals.css       # + animaciones del login (ruta y entrada)
├── components/           # Sidebar, Topbar, NavLink (cliente: enlace activo), Overview, Explorer (cliente: filtros),
│   │                     # AreaCard, Milestones, PageSection, StatCard, Badge,
│   │                     # SupplierDirectory, SupplierForm, SupplierRow (cliente: directorio de proveedores)
│   ├── incidencias/      # AnalizadorIncidencias (cliente), SelectorCsv (cliente), ResultadosAnalisis, ListaBarras,
│   │                     # TablaCruce, TablaSatisfaccion, RegistrosInvalidos
│   └── auth/             # AuthProvider, AuthGate, LoginScreen, UserMenu (cliente)
├── lib/
│   ├── data/             # areas.ts, initiatives.ts, milestones.ts, baseline.ts, suppliers.ts (valores del CONTEXT)
│   ├── initiatives.ts    # lógica pura: filterInitiatives, countByArea, countByStatus
│   ├── http.ts           # cliente HTTP de la API: fetchApi (URL base, Bearer y errores) y http (JSON; errores 422 por campo)
│   ├── session.ts        # token en sessionStorage, caducidad (`exp`) y `next` seguro
│   ├── auth.ts           # /auth/login, /auth/me, etiquetas de rol, iniciales
│   ├── suppliers.ts      # llamadas a /suppliers, validación del formulario y formato de tarifas y fechas
│   ├── incidencias.ts    # subida del CSV (FormData) y descarga de results.csv (blob)
│   ├── formato.ts        # formato es-ES del analizador (enteros, porcentajes, medias, semanas ISO)
│   └── nav.ts
├── types/                # index.ts (BusinessArea, Initiative, Milestone, Supplier…), incidencias.ts y auth.ts (usuario y token)
├── .env.example          # NEXT_PUBLIC_API_BASE_URL
└── public/logo/          # logo (copiado de uis/landing)
```

## Ejecución local

```bash
cd uis/backoffice
npm install
npm run dev      # http://localhost:3002
```

Para entrar (y para `/proveedores` e `/incidencias`) hace falta la API arrancada
([`services/api`](../../services/api/README.md), puerto 8000, con su `.env` y un usuario creado) y la URL en `.env.local` (Next.js la incrusta al compilar: tras cambiarla, reinicia `npm run dev` o repite el build). En
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

No hay tests automatizados en el repo: las pruebas en navegador se ejecutan fuera de él (Edge + `playwright-core`) y
se registran en la documentación de cada función (p. ej.
[`docs/pruebas-analizador-incidencias.md`](../../docs/pruebas-analizador-incidencias.md) y
[`docs/autenticacion.md`](../../docs/autenticacion.md#navegador-backoffice)). Comprobación de las rutas con la skill
[`validate-delivery`](../../.agents/skills/validate-delivery/SKILL.md). El HTML del panel solo trae el aviso
«Comprobando tu sesión…» (el contenido aparece tras validar el token en el navegador), así que los textos se
comprueban en `/login`:

```bash
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/login --expect "Inicia sesión" --expect "Entrar al backoffice"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/ --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/proveedores
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/incidencias
```

## Pendiente / fuera de alcance

- **Producción:** la API solo corre en local. Para publicar el login hay que desplegar antes la API, con su
  `SECRET_KEY` y un administrador, y quitar el Basic Auth del proxy delante de la API (usa la misma cabecera
  `Authorization`). Pasos en [`docs/despliegue-api.md`](../../docs/despliegue-api.md).
- **Registro:** no hay pantalla de alta. Los usuarios se crean con `POST /users` (público en la API) o
  `create-admin`, y los roles los cambia un `admin` con `PUT /users/{id}`. Riesgos pendientes en
  [`docs/autenticacion.md`](../../docs/autenticacion.md#auditoría-de-seguridad).
- Sin conexión a otros datos reales (inventario, envíos, devoluciones…): llegará con `services/` y los pipelines de
  `data/` cuando existan.
- Mantener `lib/data/` sincronizado con `CONTEXT.es.md` y `docs/hitos.md` cuando cambien.
