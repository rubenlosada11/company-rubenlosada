# Autenticación JWT y protección de rutas (AUTH-01)

Autenticación de la API [`services/api`](../services/api/README.md) y login del
[backoffice](../uis/backoffice/README.md). Práctica sin número de hito.

- **Identidad:** `User` (credenciales) y `Profile` (datos de contacto), 1 a 1, guardados **solo en TinyDB**.
- **Autenticación:** JWT firmado (HS256, `python-jose`) enviado como `Authorization: Bearer <token>`. Sin sesiones en el
  servidor y sin cookies.
- **Contraseñas:** bcrypt (`libpass[bcrypt]`, 12 rondas). Nunca se guardan ni se devuelven en claro, y el hash no sale
  en ninguna respuesta.
- **Rutas protegidas:** las 7 nuevas de usuarios, perfil y `/auth/me`, más las **8 rutas existentes** de proveedores
  e incidencias.

## Almacenamiento

```text
User    -> TinyDB (services/api/db/auth.json, tabla users)
Profile -> TinyDB (services/api/db/auth.json, tabla profiles)
```

No se ha creado ninguna tabla de usuarios, perfiles ni autenticación en Supabase/PostgreSQL. El repositorio no usa
Supabase/PostgreSQL: el ticket lo suponía, pero no existe. El `id` de cada usuario es un UUID. Es el `sub` del JWT y es
el valor que otros módulos pueden guardar como `user_uuid` para referenciar al usuario.

| `User` | `Profile` |
| --- | --- |
| `id` (UUID), `email` (único, en minúsculas), `hashed_password` (bcrypt), `is_active`, `role` (`admin` · `manager` · `user`), `created_at` (UTC) | `id` (UUID), `user_id` (→ `User.id`), `name`, `phone`, `address` |

`User` no tiene nombre, teléfono ni dirección, y `Profile` no tiene credenciales. Hay un test que comprueba las claves
exactas guardadas en TinyDB.

## Configuración

Variables de entorno de la API (plantilla en [`services/api/.env.example`](../services/api/.env.example)):

| Variable | Obligatoria | Por defecto | Qué hace |
| --- | --- | --- | --- |
| `SECRET_KEY` | **sí** | — | Clave de firma de los JWT. Mínimo 32 caracteres. Si falta, es corta o vale `change-me`, **la API no arranca** y explica cómo generar una. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `30` | Validez de cada token, en minutos enteros y mayor que 0. Se cambia sin tocar código. |
| `AUTH_DB_PATH` | no | `services/api/db/auth.json` | Fichero TinyDB de usuarios y perfiles (ignorado en git). |

En local, desde `services\api` y en Windows PowerShell (un comando por línea):

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Pega la clave generada en `SECRET_KEY=` dentro de `.env`. El `.env` está ignorado por `services/api/.gitignore` y no se
sube nunca. Para arrancar:

```powershell
uv run --env-file .env uvicorn app.main:app --reload --port 8000
```

## Primer administrador

`POST /users` es público y **siempre** crea usuarios con rol `user`: no admite `role` ni `is_active`, y si se envían
responde 422, así que nadie puede registrarse como administrador. El primer `admin` se crea desde la máquina que tiene
la base de datos:

```powershell
uv run --env-file .env create-admin carlos.vega@trackflow.test
```

Pide la contraseña dos veces, sin mostrarla. Si el email ya existe, lo convierte en `admin` y lo reactiva sin tocar su
contraseña (sirve también para recuperar el acceso si no queda ningún admin). A partir de ahí, un admin cambia roles con
`PUT /users/{id}`.

## Uso de la API

### 1. Registro — `POST /users` (público)

```json
{ "email": "laura@trackflow.test", "password": "al-menos-8-caracteres", "name": "Laura Gómez", "phone": "+34 976 000 000", "address": "Zaragoza" }
```

`name`, `phone` y `address` son opcionales. La respuesta, `201`, trae el usuario (`id`, `email`, `role: "user"`,
`is_active`, `created_at`) y su `profile`, **sin** `hashed_password`.

### 2. Login — `POST /auth/login` (público)

```json
{ "email": "laura@trackflow.test", "password": "al-menos-8-caracteres" }
```

→ `200 {"access_token": "eyJ…", "token_type": "bearer", "expires_in": 1800}`. El token contiene `sub` (id del usuario
en TinyDB), `iat` y `exp`.

`POST /auth/token` es el mismo login en formato de formulario OAuth2 (`username` = email y `password`). Es el que usa el
botón **Authorize** de Swagger UI.

### 3. Bearer token

En Windows PowerShell 5.1:

```powershell
$login = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/auth/login" -ContentType "application/json" -Body '{"email": "laura@trackflow.test", "password": "al-menos-8-caracteres"}'
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "http://localhost:8000/auth/me" -Headers $h
(Invoke-RestMethod "http://localhost:8000/suppliers?country=Spain" -Headers $h) | Format-Table id, name, rate_per_shipment
curl.exe -s -H "Authorization: Bearer $($login.access_token)" http://localhost:8000/profiles/me
```

### 4. Desde `/docs`

1. `POST /users` → *Try it out* → crear un usuario.
2. Botón **Authorize** (arriba a la derecha): email en *username* y la contraseña → *Authorize*.
3. Todas las rutas con candado envían ya el token: `GET /auth/me`, `GET /profiles/me`, `GET /suppliers`…

## Rutas

| Método | Ruta | Acceso | Autorización |
| --- | --- | --- | --- |
| POST | `/auth/login` | pública | — |
| POST | `/auth/token` | pública | — (formulario OAuth2 para Swagger) |
| GET | `/auth/me` | **Bearer** | el propio usuario (email, rol y perfil) |
| POST | `/users` | pública | siempre crea `role=user` |
| GET | `/users` | **Bearer** | `admin` o `manager`; `user` → 403 |
| GET | `/users/{id}` | **Bearer** | el propio usuario, `admin` o `manager`; otro → 403 |
| PUT | `/users/{id}` | **Bearer** | email/contraseña: solo el propio usuario · `role`/`is_active`: solo `admin` · otro → 403 |
| DELETE | `/users/{id}` | **Bearer** | el propio usuario (baja) o `admin`; borra también su perfil; otro → 403 |
| GET | `/profiles/me` | **Bearer** | solo el perfil del token (no hay ruta con `user_id`) |
| PUT | `/profiles/me` | **Bearer** | solo `name`, `phone`, `address` del propio perfil |
| POST | `/suppliers` | **Bearer** | usuario autenticado |
| GET | `/suppliers` | **Bearer** | usuario autenticado |
| GET | `/suppliers/{id}` | **Bearer** | usuario autenticado |
| PATCH | `/suppliers/{id}/rate` | **Bearer** | usuario autenticado |
| PATCH | `/suppliers/{id}/status` | **Bearer** | usuario autenticado |
| DELETE | `/suppliers/{id}` | **Bearer** | usuario autenticado |
| POST | `/api/incidents/analyze` | **Bearer** | usuario autenticado |
| GET | `/api/incidents/results/export` | **Bearer** | usuario autenticado |
| GET | `/health` | pública | — (comprobación de vida) |

La tabla sale del esquema OpenAPI de la API: las 15 rutas marcadas como Bearer llevan `security` en `/openapi.json`.

**Por qué se protegen esas 8 rutas existentes:**

- **Escrituras de proveedores** (`POST`, `PATCH …/rate`, `PATCH …/status`, `DELETE`): cambian tarifas negociadas y
  el estado de los contratos, o borran proveedores.
- **Lecturas de proveedores** (`GET /suppliers`, `GET /suppliers/{id}`): exponen tarifas negociadas, emails de
  contacto y notas internas, que son información comercial.
- **`POST /api/incidents/analyze`**: recibe el CSV del helpdesk, que contiene correos de clientes finales.
- **`GET /api/incidents/results/export`**: descarga las métricas internas de atención al cliente.

La protección se aplica a nivel de router (`dependencies=[Depends(get_current_user)]`), sin tocar los endpoints. Sus
contratos no cambian y siguen funcionando con un token válido: los 144 tests anteriores pasan autenticados.

## Errores: 401 frente a 403

| Código | Cuándo | `detail` |
| --- | --- | --- |
| 401 | Sin cabecera `Authorization` o sin `Bearer` | `No autenticado. Inicia sesión y envía el token…` |
| 401 | Token malformado, firma incorrecta, `alg: none`, sin `sub` o sin `exp` | `Token no válido.` |
| 401 | Usuario del token borrado o desactivado | `Token no válido.` (no revela el motivo) |
| 401 | Token caducado | `El token ha caducado. Inicia sesión de nuevo.` |
| 401 | Login con email inexistente o contraseña incorrecta | `Email o contraseña incorrectos.` (mismo mensaje y mismo coste bcrypt) |
| 403 | Login correcto de una cuenta desactivada | `La cuenta está desactivada. Contacta con un administrador.` |
| 403 | Usuario autenticado sobre un usuario ajeno o sin el rol necesario | p. ej. `No puedes modificar otros usuarios.` |
| 404 | `admin`/`manager` sobre un id que no existe | `Usuario no encontrado.` |
| 409 | Email ya registrado (alta o cambio de email) | `Ya existe un usuario con ese email.` |
| 422 | Email sin formato, contraseña de menos de 8 caracteres o de más de 72 bytes (límite de bcrypt), rol fuera de `admin`/`manager`/`user`, campos no permitidos | formato de validación de FastAPI |

Los 401 llevan `WWW-Authenticate: Bearer`. Los permisos se comprueban **antes** que la existencia: un `user` recibe 403
también con un id que no existe, y así no puede averiguar qué ids hay.

## Login del backoffice

El backoffice tiene ahora una pantalla propia en `/login`. Sustituye al popup de autenticación del navegador.

- **Diseño:** a pantalla completa en escritorio, con un panel de marca (logo, módulos del backoffice y la ruta animada
  entre los almacenes de Los Ángeles y Zaragoza) y una tarjeta de acceso. En móvil queda solo la tarjeta. Tiene
  mostrar/ocultar contraseña, estado «Entrando…», errores de la API en español y avisos de «sesión caducada» y
  «has cerrado sesión».
- **Panel protegido:** `/`, `/proveedores` e `/incidencias` están en el grupo de rutas `app/(panel)/` (las URLs no
  cambian). Sin una sesión válida se redirige a `/login?next=<página>` y, tras entrar, se vuelve a esa página. `next`
  solo acepta rutas internas: `//otro-dominio` lleva a `/`.
- **Sesión:** el token se guarda en `sessionStorage` (dura lo que la pestaña) y viaja en `Authorization: Bearer`
  en cada llamada a la API. Sin cookies. La sesión se cierra sola cuando caduca el token o cuando la API responde 401
  (usuario desactivado o borrado).
- **Cerrar sesión**, un solo botón por pantalla: en escritorio, una tarjeta al pie del sidebar izquierdo con
  iniciales, nombre, email, rol y el botón (`SidebarAccount`); en móvil y tablet, donde el sidebar no se muestra, en
  la barra superior con el texto «Salir» (`UserMenu`).

> La comprobación del backoffice es de interfaz. Lo que protege los datos es la API, que valida el token en cada
> petición. El contenido estático de `/` sale de `CONTEXT.es.md` y viaja en el JavaScript de la página.

## Verificación (2026-09-29)

### Tests automáticos

`uv run pytest -q` en `services/api` → **269 passed**: 144 anteriores, ahora con un cliente autenticado, más 125 de
[`tests/test_auth.py`](../services/api/tests/test_auth.py):

| Bloque | Casos |
| --- | --- |
| Usuarios | alta con perfil, contraseña hasheada con bcrypt (`$2b$`), claves exactas de `User`/`Profile` en TinyDB, email duplicado (409, sin distinguir mayúsculas), `role`/`is_active`/`id` no admitidos en el alta, validaciones 422 |
| Roles | `admin`, `manager` y `user` aceptados; `superadmin`, `Admin`, `""`, `root`, `1` rechazados; `user` por defecto; un admin asigna cada rol |
| Login | JWT válido con el id de TinyDB, expiración configurable, contraseña incorrecta, email inexistente y email sin formato con el mismo 401, contraseña de más de 72 bytes → 401 (no 500), usuario inactivo → 403, formulario OAuth2, sin cookies, esquema OAuth2 en OpenAPI |
| JWT | token válido; sin token, vacío, malformado o `Basic` → 401; caducado; firmado con otra clave; `alg: none`; sin `sub` o sin `exp`; usuario borrado, desactivado o inexistente |
| Configuración | `SECRET_KEY` ausente, vacía, `change-me` o corta → error; expiración 0, negativa o no numérica → error; la API no arranca sin `SECRET_KEY` |
| Perfiles | `GET`/`PUT /profiles/me`, cambio parcial, solo campos de perfil, sin ruta a perfiles ajenos, perfil que falta se recrea vacío |
| Autorización | rutas sin token → 401, recurso ajeno → 403 (ver, modificar, borrar, cambiar el propio rol), el propietario sí puede, operaciones de admin, 404/409 |
| Rutas existentes | las 8 rutas → 401 sin token, con token no válido y con token caducado; flujo login → proveedores/incidencias con token; `/health` pública; CORS admite `Authorization` y `PUT`, sin `allow_credentials` |
| `create-admin` | crea un admin que puede entrar, promueve uno existente sin pedir contraseña, contraseñas distintas → error |

Además se hizo una prueba de mutación: con la dependencia quitada del router de proveedores, fallan 18 tests.

### Manual contra el servidor real

`uvicorn` con un `.env` y bases TinyDB temporales, fuera del repo: **35/35** comprobaciones OK.

| Paso | Resultado |
| --- | --- |
| 1. `POST /users` (con acentos en el perfil) | 201; con `role: admin` → 422; email repetido → 409 |
| 2. `POST /auth/login` | 200 con `access_token`; contraseña mala o email inexistente → 401 con el mismo mensaje |
| 3–4. Authorize en `/docs` (email + contraseña) | «Authorized»; `GET /auth/me` desde Swagger → 200 |
| 5. `GET /auth/me` | 200 con email, rol y perfil; sin `hashed_password` |
| 6. `GET`/`PUT /profiles/me` | 200 |
| 7. Rutas existentes con token | `GET /suppliers?country=Spain`, `PATCH /suppliers/8/rate`, `POST /api/incidents/analyze` (100/95/5) y la exportación → 200 |
| Sin token | las 8 rutas existentes, `/users`, `/auth/me` y `/profiles/me` → 401 con `WWW-Authenticate: Bearer` |
| Token malformado / caducado | 401 `Token no válido.` / 401 `El token ha caducado…` |
| Recurso ajeno | `PUT`, `DELETE` y `GET /users/{otro}`, `GET /users` como `user` y cambiar el propio rol → 403; la contraseña del otro usuario no cambió |
| Arranque con `SECRET_KEY=change-me` | la API no arranca (`Application startup failed`) y muestra cómo generar una clave |
| Cookies | el login no envía `Set-Cookie` |

### Navegador (backoffice)

Edge sin interfaz con `playwright-core`, fuera del repo, contra la API y `npm run start`: **34/34** comprobaciones OK.

- **Sin sesión:** `/` → `/login?next=/`, sin mostrar el panel. Envío vacío, contraseña incorrecta y cuenta desactivada
  muestran su aviso (con `aria-invalid`); mostrar/ocultar contraseña funciona.
- **Login correcto:** `/` con «Carlos Vega · Administrador», token en `sessionStorage` y ninguna cookie.
- **Datos con token:** `/proveedores` carga los datos de la API con `Authorization: Bearer` y `/incidencias` analiza el
  CSV (95 válidos). Recargar mantiene la sesión.
- **Cierre de sesión:** **Cerrar sesión** → `/login` con aviso y sin token; `/proveedores` vuelve a pedir login y,
  tras entrar, vuelve a `/proveedores`.
- **Token caducado o con la firma manipulada:** login con «Tu sesión ha caducado» y token borrado.
- **Seguridad del `next`:** `?next=//evil.example/robar` se queda en el backoffice.
- **Móvil (390 px):** sin desbordes, panel de marca oculto y botón de cerrar sesión visible.
- **`/docs`:** Authorize y `GET /auth/me` → 200.
- Sin errores de consola, salvo los 401/403 que se provocan a propósito.

## Auditoría de seguridad

| Revisión | Resultado |
| --- | --- |
| Secretos en el código o en git | Ninguno. `SECRET_KEY` solo sale del entorno; `.env.example` lleva `change-me`, con el que la API se niega a arrancar. `.env`, `.env.local` y `db/` están ignorados (`git check-ignore`). |
| Contraseñas en claro | No se guardan (bcrypt) y no aparecen en ningún log ni respuesta; `create-admin` las pide sin eco. |
| `hashed_password` en respuestas | Nunca: las respuestas usan `UserPublic`, `ProfilePublic` y `UserWithProfile`. Hay tests en `/users`, `/auth/me` y el alta. |
| JWT | Firmado con HS256 fijo (`algorithms=["HS256"]`, así que `alg: none` y la confusión de algoritmos quedan rechazados); `exp` y `sub` obligatorios; el usuario se relee en cada petición, así que borrar o desactivar un usuario invalida sus tokens al momento. |
| Sesiones y cookies | Ninguna en la API ni en el backoffice; CORS sin `allow_credentials`. |
| Rutas sensibles públicas | Solo son públicas `POST /users`, `POST /auth/login`, `POST /auth/token` y `/health`. |
| Ownership | Comprobación explícita en `app/routes/users.py`; los perfiles solo por `/me`. |
| Mensajes de error | Login con mensaje único y tiempo igualado (verificación bcrypt de relleno); los 401 de token no dicen si el usuario existe; los 403 van antes que los 404. |
| Dependencias | `python-jose` 3.5.0 (incluye los arreglos de CVE-2024-33663 y CVE-2024-33664). `ecdsa`, dependencia transitiva, tiene un aviso de *timing* en firmas ECDSA que no aplica: solo se usa HS256. |

**Riesgos que quedan (decisiones del desarrollador, fuera del ticket):**

1. **Registro abierto + permisos amplios.** El ticket exige `POST /users` público y proteger las rutas existentes solo
   con autenticación. Si la API se publica así, cualquiera puede crear una cuenta y, con ella, editar proveedores y
   subir CSV. Antes de publicar conviene elegir una de dos opciones: cerrar el registro (solo `admin`) o exigir
   `admin`/`manager` en las escrituras de proveedores e incidencias.
2. **Sin límite de intentos de login** (fuerza bruta): añadirlo en el proxy o en la API antes de publicar.
3. **El registro revela si un email existe** (409). Es inherente a detectar duplicados.
4. **Token en `sessionStorage`:** un XSS podría leerlo. Se mitiga con React, que escapa el contenido, y porque el backoffice no usa
   `dangerouslySetInnerHTML`. Sin *refresh tokens*: al caducar hay que volver a entrar.
5. **Despliegue:** ver [`docs/despliegue-api.md`](./despliegue-api.md). Desplegar este backoffice **sin** la API
   publicada deja el panel inaccesible, porque el login necesita la API.

## Ficheros

```text
services/api/
├── .env.example              # SECRET_KEY y ACCESS_TOKEN_EXPIRE_MINUTES (placeholders)
├── app/
│   ├── auth_models.py        # Role, User, Profile y schemas de entrada/salida
│   ├── security.py           # configuración, bcrypt, creación y validación de JWT
│   ├── dependencies.py       # OAuth2PasswordBearer + get_current_user
│   ├── create_admin.py       # `uv run create-admin <email>`
│   ├── database.py           # + auth_db() (TinyDB de usuarios, candado propio)
│   ├── services/users.py     # CRUD de usuarios (alta y baja junto con el perfil)
│   ├── services/profiles.py  # CRUD de perfiles
│   └── routes/auth.py · users.py · profiles.py
└── tests/test_auth.py        # 125 tests

uis/backoffice/
├── app/login/page.tsx        # /login
├── app/(panel)/layout.tsx    # panel protegido (AuthGate + sidebar + barra superior)
├── components/auth/          # AuthProvider, AuthGate, LoginScreen, SidebarAccount, UserMenu, LogoutIcon
├── lib/session.ts            # token en sessionStorage, caducidad, `next` seguro
├── lib/auth.ts               # /auth/login, /auth/me, etiquetas de rol
└── lib/http.ts               # + Authorization: Bearer y cierre de sesión ante 401
```
