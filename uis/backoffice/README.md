# TrackFlow Backoffice

Aplicación interna de TrackFlow Tech. Muestra la estructura del negocio, el backlog de iniciativas de TrackFlow
Tech y el estado de los hitos del proyecto **a partir del contexto de empresa** (ruta `/`), el **directorio de
proveedores** (ruta `/proveedores`), el **analizador de incidencias** de CX (ruta `/incidencias`), el **gestor de
incidencias** (rutas `/gestor-incidencias` y `/gestor-incidencias/nueva`) y la **gestión de inventario** del Hito 5
(rutas `/inventory/…`, ver [Inventario](#qué-muestran-las-rutas-inventory)), estos cuatro conectados a la API [`services/api`](../../services/api/README.md). **Se entra con login** (ruta `/login`) o creando
una cuenta (ruta `/register`), con un token JWT; cada usuario edita sus datos de contacto en `/account/profile`, cambia
su contraseña en `/account/change-password` y, si la olvida, la recupera por email desde `/forgot-password` (ver
[Acceso](#acceso-login-registro-perfil-y-contraseña)).

Next.js (App Router) + React + TypeScript + Tailwind CSS, con las mismas versiones y herramientas que
[`talent-pipeline-tracker`](../talent-pipeline-tracker/README.md). Sin librerías de estado ni de UI.

> Este proyecto es independiente de [`../website`](../website/README.md): layout, estilos y datos propios; no
> comparten código.

## Demo pública

- URL: https://backofficetrackflow.rubenlosada.com/
- La versión publicada es **anterior al login** y lleva `noindex`. **No se debe redesplegar esta versión sin publicar
  antes la API**: el login la necesita y, sin ella, el panel queda inaccesible. Ver
  [`docs/despliegue-api.md`](../../docs/despliegue-api.md).

## Acceso (login, registro, perfil y contraseña)

| Ruta | Acceso | Qué hace |
| --- | --- | --- |
| `/login` | pública | Email y contraseña → `POST /auth/login` → token en `localStorage` → `GET /auth/me` → vuelve a `?next=` (solo rutas internas) o a `/`. Mensajes de la API en español (credenciales incorrectas, cuenta desactivada, API caída, sesión caducada o cerrada). |
| `/register` | pública | Email, contraseña, nombre, teléfono y dirección (opcionales) y código de invitación → `POST /users` → login automático → `/`. Errores por campo (los de la API, traducidos); 409 con enlace al login; 403 si el código no es válido. |
| `/`, `/proveedores`, `/incidencias`, `/gestor-incidencias`, `/gestor-incidencias/nueva`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders` | **privada** | Panel. Sin sesión → `/login?next=<ruta>`. |
| `/account/profile` | **privada** | `GET /auth/me`: email y rol (solo lectura) y nombre, teléfono y dirección editables con `PUT /profiles/me`. Tarjeta «Seguridad» con el acceso al cambio de contraseña. |
| `/forgot-password` | pública | AUTH-03. Email → `POST /auth/forgot-password` → «Revisa tu correo» con un mensaje **fijo** que no revela si el email existe. Se llega desde «¿Olvidaste tu contraseña?» del login. |
| `/reset-password?token=…` | pública | AUTH-03. Enlace del email (sin `Referer`). Nueva contraseña + confirmación → `POST /auth/reset-password` → `/login?motivo=restablecida`. Sin token o con un enlace no válido, caducado o usado: aviso y «Volver a recuperar contraseña». |
| `/account/change-password` | **privada** | AUTH-03. Actual + nueva + confirmación → `POST /auth/change-password`; guarda el token nuevo (la sesión sigue y las demás se cierran). Contraseña actual incorrecta → error en su campo, sin cerrar la sesión. |

| Pieza | Qué hace |
| --- | --- |
| [`components/auth/LoginScreen.tsx`](./components/auth/LoginScreen.tsx) · [`RegisterScreen.tsx`](./components/auth/RegisterScreen.tsx) · [`AuthShell.tsx`](./components/auth/AuthShell.tsx) | Pantallas públicas; `AuthShell` es el layout común (panel de marca), el campo de contraseña y los iconos. |
| [`app/(panel)/layout.tsx`](./app/(panel)/layout.tsx) + [`components/auth/AuthGate.tsx`](./components/auth/AuthGate.tsx) | Muestra el panel solo con sesión. Además, en cada cambio de ruta y al volver a la pestaña comprueba que el token sigue guardado. Las URLs no cambian (grupo de rutas). |
| [`components/auth/AuthProvider.tsx`](./components/auth/AuthProvider.tsx) | Estado de la sesión (`useAuth`): login, registro, logout, perfil y cambio de contraseña (guarda el token nuevo y reprograma su caducidad). La cierra al caducar el token, si la API responde 401 o si otra pestaña cierra sesión. |
| [`lib/session.ts`](./lib/session.ts) | Token en **`localStorage`** (sobrevive a recargas y se comparte entre pestañas; sin cookies), caducidad (`exp`) y `next` seguro. |
| [`lib/http.ts`](./lib/http.ts) | Cliente único: `Authorization: Bearer` en las peticiones protegidas; un 401 borra el token y lleva a `/login?motivo=caducada`. Login y registro van marcados como públicos. |
| [`lib/authErrors.ts`](./lib/authErrors.ts) | Traducción al español de los errores de la API en los formularios de cuenta (un mensaje desconocido se muestra tal cual). |
| [`components/auth/ProfileEditor.tsx`](./components/auth/ProfileEditor.tsx) | Formulario de `/account/profile`. |
| [`ForgotPasswordScreen.tsx`](./components/auth/ForgotPasswordScreen.tsx) · [`ResetPasswordScreen.tsx`](./components/auth/ResetPasswordScreen.tsx) · [`ChangePasswordForm.tsx`](./components/auth/ChangePasswordForm.tsx) | AUTH-03: recuperación y cambio de contraseña. Reglas compartidas con el registro en [`lib/authRules.ts`](./lib/authRules.ts). |
| [`components/auth/SidebarAccount.tsx`](./components/auth/SidebarAccount.tsx) · [`UserMenu.tsx`](./components/auth/UserMenu.tsx) | Escritorio: tarjeta al pie del sidebar con **Mi perfil** y **Cerrar sesión**. Móvil: el avatar lleva al perfil y **Salir** cierra la sesión. |

**Mejora adicional (fuera del enunciado de AUTH-02):** si la API tiene `REGISTRATION_CODE`, el registro exige ese
código de invitación; sin él, el registro es abierto, como pide el ticket y como funciona en local. El
primer administrador se crea con `uv run --env-file .env create-admin <email>` en `services\api`. Detalle, permisos y
verificación: [`docs/autenticacion.md`](../../docs/autenticacion.md). La comprobación del backoffice es de interfaz:
los datos los protege la API, que valida el token en cada petición.

## Qué muestra la ruta `/`

| Sección | Contenido | Fuente |
| --- | --- | --- |
| Resumen | Datos de partida del briefing (empleados, almacenes, transportistas, % de devoluciones y de consultas automatizables, facturación) y resumen del backlog calculado a partir de los datos (áreas, iniciativas, por estado). | `CONTEXT.es.md` |
| Áreas de negocio | Las 7 áreas, con responsable, equipo y situación actual. Cada tarjeta filtra las iniciativas de su área. | `CONTEXT.es.md` |
| Iniciativas | 33 necesidades de las áreas (“Qué necesitan”) con filtros por área y estado, contador y estado vacío. Estados: *Necesidad identificada* / *Base técnica disponible* (4 iniciativas: 3 con base en `packages/shared`, Hito 2, y la API de inventario unificada, Hito 5). | `CONTEXT.es.md` + `packages/shared` + `services/api` |
| Hitos del proyecto | Hitos 1–5 con estado, ubicación en el monorepo y demo pública (el 5, en curso y sin demo). | `docs/hitos.md` |

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
| Alta con validación en cliente; los errores 422 de la API se muestran junto a su campo, en español. La moneda la fija el país | `POST /suppliers` |
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

## Qué muestran las rutas `/gestor-incidencias` y `/gestor-incidencias/nueva`

Gestor centralizado de incidencias, según [`CONTEXT-gestor-incidencias.es.md`](../../CONTEXT-gestor-incidencias.es.md).
Documentación completa: [`docs/gestor-incidencias.md`](../../docs/gestor-incidencias.md). No es el analizador de
`/incidencias`: aquel calcula métricas de un CSV sin guardar nada; este guarda incidencias y gestiona su estado.

| Función | Llamada a la API |
| --- | --- |
| **Formulario** (`/nueva`): título, descripción, categoría, origen y sede, todos obligatorios; validación en cliente con los mensajes de la API; la sede se destaca cuando el origen es «Sede»; botón deshabilitado durante el envío; confirmación con el número y formulario limpio | `POST /api/incidents` |
| **Listado**: de la más reciente a la más antigua, con filtros por estado, origen, sede y categoría, sin recargar la página; estados de carga, vacío y error con «Reintentar» | `GET /api/incidents?status=…&origin=…&branch=…&category=…` |
| **Cambio de estado** desde la fila, solo con las transiciones permitidas. Es optimista: la fila cambia al instante y vuelve al estado anterior, con el motivo, si la API falla o lo rechaza | `PATCH /api/incidents/{id}/status` |
| **Resumen**: tarjetas por estado y barras por categoría, sede y origen, con su propia carga y su propio error (si falla, el listado sigue funcionando); se actualiza tras cada cambio de estado | `GET /api/incidents/summary` |

Los controles del formulario miden 48 px de alto para los terminales táctiles del almacén. Los errores 400 de la API se
muestran junto a su campo; los del servidor (5xx) se sustituyen por un mensaje fijo, sin trazas ni JSON. Las etiquetas
de las sedes son las del CONTEXT. Capturas:
[formulario con error de validación](./screenshots/screenshot%20gestor%20formulario%20validacion.png),
[listado con datos](./screenshots/screenshot%20gestor%20listado.png) y
[resumen con métricas](./screenshots/screenshot%20gestor%20resumen.png).

## Qué muestran las rutas `/inventory/…`

Interfaz del inventario unificado de Los Ángeles y Zaragoza (Hito 5), sobre la API `/inventory` ya existente.
Entidades, campos y reglas: [`CONTEXT-gestor-inventario.es.md`](../../CONTEXT-gestor-inventario.es.md); API y
decisiones: [`docs/inventario.md`](../../docs/inventario.md). En el menú: **Inventario** e **Historial de movimientos**;
cada página enlaza además con las otras tres. `/inventory` lleva al listado de productos.

| Ruta | Qué hace | Llamada a la API |
| --- | --- | --- |
| `/inventory/products` | SKUs con nombre, código, cliente, categoría, almacén y **`current_stock`** (el del almacén del SKU; si hay unidades en el otro almacén se indican aparte, nunca sumadas). Indicador de nivel con color y texto: *Stock saludable*, *Stock bajo*, *Stock crítico* o *Agotado*, y tarjetas con el recuento. Cada fila tiene **Registrar entrada** y **Registrar salida** (`?sku_id=<id>`). Carga, error con «Reintentar», listado vacío y «Actualizar» (un fallo al actualizar conserva la tabla) | `GET /inventory/products` |
| `/inventory/orders/inbound` | Recepción de mercancía: producto (selector por nombre · SKU · almacén, nunca un id escrito a mano), cantidad y referencia del cliente. Muestra el stock actual del producto elegido. Confirmación con el stock nuevo y formulario limpio; los errores conservan lo escrito | `GET /inventory/products`, `GET /inventory/products/{id}`, `POST /inventory/orders/inbound` |
| `/inventory/orders/outbound` | Despacho o pérdida: producto, tipo de salida, número de seguimiento (solo en despachos) y cantidad. Al elegir producto se pide su stock a la API y se muestra antes de escribir la cantidad; si la cantidad lo supera (o el producto está agotado) aparece un aviso junto al campo y no se puede enviar. El **400 de stock insuficiente** de la API se muestra en español junto a la cantidad, sin limpiar el formulario, y se vuelve a pedir el stock | `GET /inventory/products`, `GET /inventory/products/{id}`, `POST /inventory/orders/outbound` |
| `/inventory/orders` | Historial **de solo lectura**: fecha, tipo (entrada / salida con su tipo, con color, icono, signo y texto), producto, almacén, cantidad, referencia o seguimiento y `user_uuid` (marcado «Tú» si es el usuario conectado). Filtros de la API por almacén y producto | `GET /inventory/orders?warehouse=…&sku_id=…` |

- **Una sola capa de integración:** [`lib/inventory.ts`](./lib/inventory.ts) (`inventoryApi`). Usa `lib/http.ts`, que
  añade el Bearer de la sesión y gestiona 401, tiempo máximo y errores de red. Ningún componente llama a `fetch`. Las
  respuestas se comprueban antes de mostrarlas: un 200 con otra forma da un mensaje legible.
- **Umbrales de stock:** son **de presentación, no reglas de negocio** (el CONTEXT no define mínimos):
  agotado ≤ 0, crítico 1–10, bajo 11–30 y saludable > 30, en `STOCK_THRESHOLDS` de `lib/inventory.ts`.
- **Cambios rápidos de producto en la salida:** cada consulta de stock se cancela al cambiar de producto y su
  resultado solo se usa si corresponde a la selección actual. Mientras llega se muestra «Consultando el stock
  actual…», nunca el stock del producto anterior.
- **La API manda:** la validación de cliente es una ayuda; el backend vuelve a comprobar el stock (regla 2) y su
  respuesta es la definitiva.
- Las entradas y salidas se registran en el almacén del SKU (la API lo usa por defecto; el formulario no envía
  `warehouse`).
- Fechas en `es-ES` y en la zona horaria del navegador, como el gestor de incidencias.
- Capturas en [`screenshots/gestión de inventario/`](./screenshots/gesti%C3%B3n%20de%20inventario/): [listado](./screenshots/gesti%C3%B3n%20de%20inventario/Listado%20de%20productos.jpeg), [entrada](./screenshots/gesti%C3%B3n%20de%20inventario/Registro%20de%20entrada%20producto%20confirmaci%C3%B3n%20y%20stock%20actual.jpeg), [aviso de stock](./screenshots/gesti%C3%B3n%20de%20inventario/Registro%20de%20salida%20con%20aviso%20de%20stock.jpeg), [400 de la API](./screenshots/gesti%C3%B3n%20de%20inventario/Registro%20salida%20pesta%C3%B1a%20A%20enviada%20y%20aviso%20stock.jpeg), [historial](./screenshots/gesti%C3%B3n%20de%20inventario/Historial%20de%20movimientos%20completo.jpeg) y [ruta protegida](./screenshots/gesti%C3%B3n%20de%20inventario/Ruta%20protegida.png); las diez, con qué muestra cada una, en [`docs/inventario.md`](../../docs/inventario.md#interfaz-en-el-backoffice).

## Qué ocurre cuando algo falla

Todas las pantallas que llaman a la API muestran un mensaje en español, sin códigos HTTP ni detalles técnicos, y una
salida («Reintentar», «Volver al inicio» o el menú). Capturas:
[error interno de la API](./screenshots/screenshot%20errores%20servidor.png) (ya no se confunde con una API apagada),
[API que no responde](./screenshots/screenshot%20errores%20sin%20conexion.png),
[error de validación de la API en su campo](./screenshots/screenshot%20errores%20validacion.png) y
[página no encontrada](./screenshots/screenshot%20errores%20404.png).

## Estructura

```text
backoffice/
├── app/
│   ├── layout.tsx        # fuentes, `noindex` (herramienta interna) y AuthProvider
│   ├── login/page.tsx    # ruta `/login`
│   ├── register/page.tsx # ruta `/register`
│   ├── forgot-password/page.tsx  # ruta `/forgot-password` (AUTH-03)
│   ├── reset-password/page.tsx   # ruta `/reset-password?token=…` (AUTH-03)
│   ├── (panel)/          # grupo de rutas protegido (no cambia las URLs)
│   │   ├── layout.tsx    # AuthGate + sidebar + barra superior
│   │   ├── page.tsx      # ruta `/`
│   │   ├── proveedores/page.tsx  # ruta `/proveedores`
│   │   ├── incidencias/page.tsx  # ruta `/incidencias`
│   │   ├── gestor-incidencias/page.tsx        # ruta `/gestor-incidencias` (resumen + listado)
│   │   ├── gestor-incidencias/nueva/page.tsx  # ruta `/gestor-incidencias/nueva` (formulario)
│   │   ├── inventory/    # `/inventory` (→ products), products/, orders/ (historial), orders/inbound/, orders/outbound/
│   │   ├── account/profile/page.tsx  # ruta `/account/profile`
│   │   └── account/change-password/page.tsx  # ruta `/account/change-password` (AUTH-03)
│   ├── error.tsx, global-error.tsx, not-found.tsx  # límites de error y 404 (también `(panel)/error.tsx`, con el menú)
│   └── globals.css       # + animaciones del login (ruta y entrada)
├── components/           # Sidebar, Topbar, NavLink (cliente: enlace activo), Overview, Explorer (cliente: filtros),
│   │                     # AreaCard, Milestones, PageSection, StatCard, Badge, ErrorPanel (pantallas de error y 404),
│   │                     # SupplierDirectory, SupplierForm, SupplierRow (cliente: directorio de proveedores)
│   ├── incidencias/      # AnalizadorIncidencias (cliente), SelectorCsv (cliente), ResultadosAnalisis, ListaBarras,
│   │                     # TablaCruce, TablaSatisfaccion, RegistrosInvalidos
│   ├── gestor-incidencias/  # IncidentForm, IncidentDashboard, IncidentSummary, IncidentList (cliente), IncidentRow
│   ├── inventory/        # ProductList, InboundForm, OutboundForm, MovementHistory (cliente), formParts (selector de
│   │                     # producto, ficha de stock, useProducts, useProductStock), StockBadge, InventoryHeader
│   └── auth/             # AuthProvider, AuthGate, AuthShell, LoginScreen, RegisterScreen, ProfileEditor,
│                         # SidebarAccount, UserMenu (cliente), LogoutIcon, ForgotPasswordScreen,
│                         # ResetPasswordScreen, ChangePasswordForm
├── lib/
│   ├── data/             # areas.ts, initiatives.ts, milestones.ts, baseline.ts, suppliers.ts (valores del CONTEXT),
│   │                     # incidents.ts (sedes, categorías, orígenes, estados y transiciones del gestor),
│   │                     # inventory.ts (almacenes, categorías y tipos de salida del inventario)
│   ├── initiatives.ts    # lógica pura: filterInitiatives, countByArea, countByStatus
│   ├── http.ts           # cliente HTTP de la API: fetchApi (URL base, Bearer, tiempo máximo y errores), http (JSON;
│   │                     # errores de validación por campo, en español) y apiErrorMessage (mensaje para el usuario)
│   ├── session.ts        # token en localStorage, caducidad (`exp`) y `next` seguro
│   ├── auth.ts           # /auth/login, /users, /auth/me, /profiles/me, recuperación y cambio de contraseña, roles
│   ├── authRules.ts      # reglas de email y contraseña (las mismas que la API)
│   ├── authErrors.ts     # errores de la API en español para los formularios de cuenta
│   ├── suppliers.ts      # llamadas a /suppliers, validación del formulario y formato de tarifas y fechas
│   ├── incidencias.ts    # subida del CSV (FormData) y descarga de results.csv (blob)
│   ├── incidents.ts      # gestor: llamadas a /api/incidents, validación del formulario y mensajes de error
│   ├── inventory.ts      # inventario: inventoryApi (/inventory), umbrales de stock, validaciones y errores
│   ├── formato.ts        # formato es-ES del analizador (enteros, porcentajes, medias, semanas ISO)
│   └── nav.ts
├── types/                # index.ts (BusinessArea, Initiative, Milestone, Supplier…), incidencias.ts (analizador),
│                         # incidents.ts (gestor), inventory.ts (inventario) y auth.ts (usuario y token)
├── .env.example          # NEXT_PUBLIC_API_BASE_URL y NEXT_PUBLIC_INVENTORY_API_URL
└── public/logo/          # logo (copiado de uis/landing)
```

## Ejecución local

```bash
cd uis/backoffice
npm install
npm run dev      # http://localhost:3002
```

Para entrar (y para `/proveedores`, `/incidencias`, `/gestor-incidencias` e `/inventory`) hace falta la API arrancada
([`services/api`](../../services/api/README.md), puerto 8000, con su `.env` y un usuario creado) y la URL en `.env.local` (Next.js la incrusta al compilar: tras cambiarla, reinicia `npm run dev` o repite el build). En
Windows PowerShell:

```powershell
Copy-Item .env.example .env.local
```

Variables (`.env.example`; las dos van al navegador, así que **nunca** llevan tokens ni claves):

| Variable | Valor local | Para qué |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API de TrackFlow: login y todas las secciones |
| `NEXT_PUBLIC_INVENTORY_API_URL` | `http://localhost:8000` | API del inventario. Opcional: vacía o sin definir, se usa `NEXT_PUBLIC_API_BASE_URL` (hoy es la misma API y valida el mismo token) |

Para tener datos en el inventario, en `services\api`: `uv run seed-inventory` (necesita un usuario creado; ver
[`docs/inventario.md`](../../docs/inventario.md)).

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
npm test            # Jest: tests unitarios de lib/ (lib/*.test.ts)
npm run test:coverage
npm run build
```

Los tests unitarios de Jest (`jest.config.mjs` con `next/jest`, entorno `node`) cubren las utilidades de `lib/`:
sesión, reglas y errores de autenticación (AUTH-088), validación y formato de proveedores e incidencias (FE-019) y la
capa del inventario (`lib/inventory.test.ts`: peticiones con Bearer, URL, cuerpos, 400/401/403/404/422/500, error de
red, respuestas vacías e inesperadas, umbrales y validaciones; Hito 5). Plan,
casos y resultados en [`TESTING.md`](../../TESTING.md). Las pruebas en navegador se ejecutan fuera del repo (Edge +
`playwright-core`) y se registran en la documentación de cada función (p. ej.
[`docs/pruebas-analizador-incidencias.md`](../../docs/pruebas-analizador-incidencias.md),
[`docs/gestor-incidencias.md`](../../docs/gestor-incidencias.md#tests) y
[`docs/autenticacion.md`](../../docs/autenticacion.md#navegador-backoffice)). Comprobación de las rutas con la skill
[`validate-delivery`](../../.agents/skills/validate-delivery/SKILL.md). El HTML del panel solo trae el aviso
«Comprobando tu sesión…» (el contenido aparece tras validar el token en el navegador), así que los textos se
comprueban en `/login`:

```bash
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/login --expect "Inicia sesión" --expect "Entrar al backoffice"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/register --expect "Crea tu cuenta" --expect "Código de invitación"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/ --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/account/profile --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/forgot-password --expect "¿Olvidaste tu contraseña?" --expect "Enviar enlace"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs "http://localhost:3002/reset-password?token=prueba" --expect "Elige una contraseña nueva"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/account/change-password --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/proveedores
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/incidencias
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/gestor-incidencias
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/gestor-incidencias/nueva
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/inventory/products --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/inventory/orders/inbound --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/inventory/orders/outbound --expect "Comprobando tu sesión"
node ../../.agents/skills/validate-delivery/scripts/check-route.mjs http://localhost:3002/inventory/orders --expect "Comprobando tu sesión"
```

## Pendiente / fuera de alcance

- **Producción:** la API solo corre en local. Para publicar el login hay que desplegar antes la API, con su
  `SECRET_KEY` y un administrador, y quitar el Basic Auth del proxy delante de la API (usa la misma cabecera
  `Authorization`). Pasos en [`docs/despliegue-api.md`](../../docs/despliegue-api.md).
- **Registro:** `/register` crea siempre usuarios con rol `user`; los roles los cambia un `admin` con
  `PUT /users/{id}` (sin pantalla). **Antes de publicar, definir `REGISTRATION_CODE` en la API** para que no se pueda
  registrar cualquiera. Riesgos pendientes en
  [`docs/autenticacion.md`](../../docs/autenticacion.md#auditoría-de-seguridad).
- Cambiar el email: la API lo permite (`PUT /users/{id}` con `current_password`), pero no hay pantalla. La contraseña
  sí tiene pantalla (`/account/change-password`, AUTH-03).
- Recuperación de contraseña en producción: la API necesita `RESEND_API_KEY`, `MAIL_FROM` y `FRONTEND_BASE_URL` con la
  URL pública del backoffice (ver [`docs/autenticacion.md`](../../docs/autenticacion.md#recuperación-y-cambio-de-contraseña-auth-03)).
- Gestor de incidencias: sin paginación, edición ni borrado, y sin las alertas de incidencias sin resolver que
  menciona el CONTEXT (ver [`docs/gestor-incidencias.md`](../../docs/gestor-incidencias.md#limitaciones)).
- Inventario: sin alta de SKUs en la interfaz (la API tiene `POST /inventory/products`; no lo pide el hito), sin
  paginación, sin elegir un almacén distinto del del SKU en los movimientos y sin permisos por rol (cualquier usuario
  autenticado registra movimientos). El historial muestra el `user_uuid`, no el nombre (no hay un endpoint de usuarios
  para cualquier rol). Si se entra sin sesión a un formulario con `?sku_id=`, tras el login se vuelve al formulario sin
  el producto (el `next` del login guarda la ruta, no la consulta). Umbrales de stock orientativos (ver arriba).
- Sin conexión a otros datos reales (envíos, devoluciones…): llegará con `services/` y los pipelines de `data/`
  cuando existan.
- Mantener `lib/data/` sincronizado con `CONTEXT.es.md` y `docs/hitos.md` cuando cambien.
