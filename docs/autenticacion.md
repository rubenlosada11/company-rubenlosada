# Autenticación JWT y protección de rutas (AUTH-01, AUTH-02 y AUTH-03)

Autenticación de la API [`services/api`](../services/api/README.md) (AUTH-01), flujos de autenticación del
[backoffice](../uis/backoffice/README.md): login, registro, perfil, logout y vistas protegidas (AUTH-02, ver
[Backoffice](#backoffice-auth-02)), y recuperación y cambio de contraseña con emails reales (AUTH-03, ver
[Recuperación y cambio de contraseña](#recuperación-y-cambio-de-contraseña-auth-03)). Práctica sin número de hito.

- **Identidad:** `User` (credenciales) y `Profile` (datos de contacto), 1 a 1, guardados **solo en TinyDB**.
- **Autenticación:** JWT firmado (HS256, `python-jose`) enviado como `Authorization: Bearer <token>`. Sin sesiones en el
  servidor y sin cookies.
- **Contraseñas:** bcrypt (`libpass[bcrypt]`, 12 rondas). Nunca se guardan ni se devuelven en claro, y el hash no sale
  en ninguna respuesta.
- **Rutas protegidas:** las 7 nuevas de usuarios, perfil y `/auth/me`, más las **8 rutas existentes** de proveedores
  e incidencias.

## Almacenamiento

```text
User               -> TinyDB (services/api/db/auth.json, tabla users)
Profile            -> TinyDB (services/api/db/auth.json, tabla profiles)
PasswordResetToken -> TinyDB (services/api/db/auth.json, tabla password_reset_tokens)   # AUTH-03
```

No se ha creado ninguna tabla de usuarios, perfiles ni autenticación en Supabase/PostgreSQL. El repositorio no usa
Supabase/PostgreSQL: el ticket lo suponía, pero no existe. El `id` de cada usuario es un UUID. Es el `sub` del JWT y es
el valor que otros módulos pueden guardar como `user_uuid` para referenciar al usuario.

| `User` | `Profile` |
| --- | --- |
| `id` (UUID), `email` (único, en minúsculas), `hashed_password` (bcrypt), `is_active`, `role` (`admin` · `manager` · `user`), `created_at` (UTC) | `id` (UUID), `user_id` (→ `User.id`), `name`, `phone`, `address` |

`User` no tiene nombre, teléfono ni dirección, y `Profile` no tiene credenciales. Hay un test que comprueba las claves
exactas guardadas en TinyDB.

AUTH-03 añade a `User` el campo opcional `password_changed_at` (solo existe tras el primer cambio de contraseña) y la
tabla `password_reset_tokens` (`id`, `user_id`, `token_hash`, `created_at`, `expires_at`, `used_at`). TinyDB no tiene
esquema ni migraciones: la tabla se crea en el primer uso y los usuarios anteriores se leen igual.

## Configuración

Variables de entorno de la API (plantilla en [`services/api/.env.example`](../services/api/.env.example)):

| Variable | Obligatoria | Por defecto | Qué hace |
| --- | --- | --- | --- |
| `SECRET_KEY` | **sí** | — | Clave de firma de los JWT. Mínimo 32 caracteres. Si falta, es corta o vale `change-me`, **la API no arranca** y explica cómo generar una. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `30` | Validez de cada token, en minutos enteros y mayor que 0. Se cambia sin tocar código. |
| `AUTH_DB_PATH` | no | `services/api/db/auth.json` | Fichero TinyDB de usuarios y perfiles (ignorado en git). |
| `REGISTRATION_CODE` | no (**sí antes de publicar**) | — (registro abierto) | *Mejora adicional de AUTH-02, fuera del enunciado.* Código de invitación que exige `POST /users`. Mínimo 12 caracteres: si es más corto, **la API no arranca**. Vacío o sin definir = registro abierto (desarrollo local). |
| `RESEND_API_KEY` | no (sí para enviar emails) | — | AUTH-03. Clave de [Resend](https://resend.com) (basta permiso *Sending access*). Sin ella la API arranca, pero no envía emails de recuperación y lo avisa en el log. Solo en `.env`: nunca en git ni en el frontend. |
| `MAIL_FROM` | sí, si hay `RESEND_API_KEY` | — | AUTH-03. Remitente `direccion@dominio` o `Nombre <direccion@dominio>`, de un dominio verificado en Resend. **Entre comillas dobles** en el `.env` (`MAIL_FROM="TrackFlow <no-reply@dominio>"`): sin ellas `uv run --env-file` descarta esa línea y las siguientes. Con clave y sin un remitente válido, **la API no arranca**. |
| `FRONTEND_BASE_URL` | no | `http://localhost:3002` | AUTH-03. URL pública del backoffice: el email enlaza a `<FRONTEND_BASE_URL>/reset-password?token=…`. Debe empezar por `http://` o `https://`; si no, la API no arranca. |
| `RESET_TOKEN_EXPIRE_MINUTES` | no | `30` | AUTH-03. Validez de los enlaces de recuperación, entre 15 y 60 minutos; fuera de ese rango la API no arranca. |

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

**Código de invitación (mejora adicional, fuera del enunciado de AUTH-02; ver
[Mejora adicional](#mejora-adicional-código-de-invitación-registration_code)).** Si la API tiene `REGISTRATION_CODE`, el cuerpo debe incluir
`"invitation_code": "<código>"`; si falta o no coincide → `403 {"detail": "Código de invitación no válido."}`. Se
comprueba en tiempo constante (`hmac.compare_digest`) y **antes** que el email, así que sin el código no se puede
averiguar si un email está registrado (403, nunca 409). El código no se guarda. Sin `REGISTRATION_CODE`, el campo es
opcional y se ignora.

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
| POST | `/auth/forgot-password` | pública | AUTH-03 · siempre 200 con el mismo mensaje; solo envía el enlace si el email es de un usuario activo |
| POST | `/auth/reset-password` | pública | AUTH-03 · con el token del email; un solo uso; cierra todas las sesiones del usuario |
| POST | `/auth/change-password` | **Bearer** | AUTH-03 · el propio usuario (sin id en la petición); exige la contraseña actual; devuelve un token nuevo |
| POST | `/users` | pública | siempre crea `role=user`; con `REGISTRATION_CODE`, exige `invitation_code` |
| GET | `/users` | **Bearer** | `admin` o `manager`; `user` → 403 |
| GET | `/users/{id}` | **Bearer** | el propio usuario, `admin` o `manager`; otro → 403 |
| PUT | `/users/{id}` | **Bearer** | email: solo el propio usuario y **con `current_password`** (AUTH-03) · `role`/`is_active`: solo `admin` · otro → 403 · ya **no** admite `password` (422) |
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

La tabla sale del esquema OpenAPI de la API: las 16 rutas marcadas como Bearer llevan `security` en `/openapi.json`.

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
| 400 | `POST /auth/reset-password` con un enlace inexistente, manipulado, caducado, ya usado o de una cuenta desactivada (AUTH-03) | `El enlace para restablecer la contraseña no es válido o ha caducado. Solicita uno nuevo.` (un solo mensaje: no da pistas) |
| 400 | `POST /auth/change-password` o cambio de email con la contraseña actual incorrecta (AUTH-03) | `La contraseña actual no es correcta.` (400 y no 401: la sesión es válida y el backoffice no la cierra) |
| 400 | Cambio de email sin `current_password` (AUTH-03) | `Para cambiar el email, indica tu contraseña actual (current_password).` |
| 401 | Sin cabecera `Authorization` o sin `Bearer` | `No autenticado. Inicia sesión y envía el token…` |
| 401 | Token emitido antes del último cambio o restablecimiento de contraseña (AUTH-03) | `Token no válido.` |
| 401 | Token malformado, firma incorrecta, `alg: none`, sin `sub` o sin `exp` | `Token no válido.` |
| 401 | Usuario del token borrado o desactivado | `Token no válido.` (no revela el motivo) |
| 401 | Token caducado | `El token ha caducado. Inicia sesión de nuevo.` |
| 401 | Login con email inexistente o contraseña incorrecta | `Email o contraseña incorrectos.` (mismo mensaje y mismo coste bcrypt) |
| 403 | Login correcto de una cuenta desactivada | `La cuenta está desactivada. Contacta con un administrador.` |
| 403 | Registro sin código de invitación válido (solo con `REGISTRATION_CODE`) | `Código de invitación no válido.` |
| 403 | Usuario autenticado sobre un usuario ajeno o sin el rol necesario | p. ej. `No puedes modificar otros usuarios.` |
| 404 | `admin`/`manager` sobre un id que no existe | `Usuario no encontrado.` |
| 409 | Email ya registrado (alta o cambio de email) | `Ya existe un usuario con ese email.` |
| 422 | Email sin formato, contraseña de menos de 8 caracteres o de más de 72 bytes (límite de bcrypt), rol fuera de `admin`/`manager`/`user`, campos no permitidos (también `password` en `PUT /users/{id}`), contraseña nueva igual a la actual | formato de validación de FastAPI |

Los 401 llevan `WWW-Authenticate: Bearer`. Los permisos se comprueban **antes** que la existencia: un `user` recibe 403
también con un id que no existe, y así no puede averiguar qué ids hay.

## Backoffice (AUTH-02)

El login del backoffice llegó con AUTH-01; AUTH-02 (2026-10-01) completa el ciclo: registro, perfil, token en
`localStorage` y protección de vistas. Solo afecta a `uis/backoffice`: **`uis/website` y `uis/landing` siguen siendo
públicas** y no leen ni escriben ningún almacenamiento (comprobado en el navegador).

### Alcance de la entrega

| Requisito del enunciado de AUTH-02 | Dónde | Estado |
| --- | --- | --- |
| Login (`POST /auth/login`) con email y contraseña | `/login` | ✅ |
| Registro (`POST /users` + `POST /auth/login` automático) con los campos que admite la API | `/register` | ✅ |
| JWT guardado en `localStorage` | `lib/session.ts` | ✅ |
| `Authorization: Bearer` centralizado en las llamadas protegidas | `lib/http.ts` | ✅ |
| Vistas privadas protegidas (sin middleware) | `app/(panel)/` + `AuthGate` | ✅ |
| Perfil: `GET /auth/me` y edición con `PUT /profiles/me` | `/account/profile` | ✅ |
| Logout (token borrado, estado limpio, `/login`) | sidebar y barra superior | ✅ |
| 401 → limpiar la sesión y volver a `/login`, sin bucles | `lib/http.ts` + `AuthProvider` | ✅ |
| Website del Hito 1 completamente público | `uis/landing` (y `uis/website`) sin cambios | ✅ |
| **Mejora adicional (no pedida):** código de invitación para registrarse | API + `/register` | ✅ ver abajo |

### Mejora adicional: código de invitación (`REGISTRATION_CODE`)

**No forma parte del enunciado de AUTH-02**, que pide un registro público. La añadimos para completar y enriquecer el
proyecto, a raíz de una pregunta del desarrollador durante el diseño: «¿crear cuenta puede hacerlo cualquiera?». Con el
registro abierto, si se publica la demo, cualquiera puede crearse una cuenta y entrar en el panel interno.

- **Opciones valoradas:** registro abierto (lo que pide el ticket); código validado **en la API** (elegida); código
  validado solo en el frontend (descartada: cualquiera puede llamar a `POST /users` directamente y saltárselo).
- **Compatible con el enunciado:** la variable es **opcional**. Sin ella, el registro es abierto exactamente como pide
  el ticket (y así funcionan el entorno local y los 269 tests anteriores). Con ella, `POST /users` exige
  `invitation_code` y responde 403 si falta o no coincide.
- **Seguridad:** mínimo 12 caracteres (si no, la API no arranca), comparación en tiempo constante
  (`hmac.compare_digest`), comprobación antes que el email (sin código no se puede averiguar qué emails existen) y el
  código nunca se guarda.
- **Coste:** 3 ficheros de la API (`security.py`, `auth_models.py`, `routes/users.py`), 18 tests nuevos y un campo más
  en `/register`. Detalle de la API en [Registro](#1-registro--post-users-público).

| Ruta | Acceso | Flujo |
| --- | --- | --- |
| `/login` | pública | `POST /auth/login` → token en `localStorage` → `GET /auth/me` → `?next=` (solo rutas internas) o `/` |
| `/register` | pública | `POST /users` (con `invitation_code` si hace falta) → `POST /auth/login` → token → `/` |
| `/`, `/proveedores`, `/incidencias` | **privada** | grupo de rutas `app/(panel)/` con `AuthGate`; sin sesión → `/login?next=<ruta>` |
| `/account/profile` | **privada** | `GET /auth/me` (email y rol de solo lectura) y `PUT /profiles/me` (`name`, `phone`, `address`) |

- **Diseño:** login y registro a pantalla completa en escritorio, con un panel de marca (logo, módulos del backoffice y
  la ruta animada entre los almacenes de Los Ángeles y Zaragoza) y una tarjeta. En móvil queda solo la tarjeta.
  Mostrar/ocultar contraseña, estados «Entrando…» / «Creando tu cuenta…» / «Guardando…» y avisos de «sesión
  caducada» y «has cerrado sesión».
- **Token:** en `localStorage` (requisito del ticket; antes `sessionStorage`). Sobrevive a recargas y a cerrar el
  navegador, se comparte entre pestañas y su vida la limita el `exp` del JWT. Solo se lee en el navegador (efectos y
  eventos), nunca en el render del servidor. Sin cookies y **sin middleware de Next.js** (no puede leer
  `localStorage`).
- **Cliente HTTP único** (`lib/http.ts`): todas las llamadas protegidas llevan `Authorization: Bearer`. Login y
  registro van marcados como públicos (`{ auth: false }`), así que su 401/403 es un error del formulario y no cierra
  ninguna sesión.
- **Cierre de sesión automático**, siempre con `/login?next=<ruta>&motivo=caducada`:
  - la API responde **401** a cualquier petición protegida (token caducado, manipulado, ausente o de un usuario
    desactivado o borrado);
  - el token llega a su `exp` (temporizador, aunque no haya peticiones);
  - el token ya no está en `localStorage` al cambiar de ruta o al volver a la pestaña;
  - otra pestaña cierra sesión (evento `storage`). Si otra pestaña inicia sesión, esta la recoge.
- **Registro:** campos exactos de `POST /users`; validación en cliente de lo obligatorio, el formato del email y la
  longitud de la contraseña (incluido el límite de 72 bytes); el resto lo valida la API. Errores por campo con los
  mensajes de la API traducidos (`lib/authErrors.ts`; un mensaje desconocido se muestra tal cual), 409 con enlace al
  login y 403 en el campo del código. Si el alta va bien pero falla el login automático, la pantalla lo dice y lleva
  al login.
- **Perfil:** «Guardar» solo con cambios; un campo vacío se envía como `null` (borra el dato); tras guardar, el
  nombre del sidebar se actualiza.
- **Cerrar sesión**, un solo botón por pantalla: en escritorio, una tarjeta al pie del sidebar con iniciales, nombre,
  email, rol, **Mi perfil** y **Cerrar sesión** (`SidebarAccount`); en móvil y tablet, en la barra superior: el avatar
  lleva al perfil y «Salir» cierra la sesión (`UserMenu`). Borra el token, limpia el estado y lleva a `/login`.

> La comprobación del backoffice es de interfaz. Lo que protege los datos es la API, que valida el token en cada
> petición. El contenido estático de `/` sale de `CONTEXT.es.md` y viaja en el JavaScript de la página.

## Recuperación y cambio de contraseña (AUTH-03)

AUTH-03 (2026-10-01/02) añade recuperar una contraseña olvidada con un enlace temporal enviado por email y cambiarla
estando autenticado. Trabajo por fases con parada y confirmación del desarrollador. Solo cambian `services/api` y
`uis/backoffice`; **`uis/website` y `uis/landing` siguen públicas y sin cambios**.

```text
/login → «¿Olvidaste tu contraseña?» → /forgot-password → POST /auth/forgot-password → 200 (mensaje genérico)
      → email (Resend) → /reset-password?token=… → POST /auth/reset-password → enlace usado → /login?motivo=restablecida

/account/change-password (con sesión) → POST /auth/change-password (actual + nueva) → token nuevo → sigue dentro
```

### Decisiones de seguridad

| Decisión | Motivo |
| --- | --- |
| `forgot-password` responde **siempre** 200 con el mismo cuerpo y cabeceras; el email sale en `BackgroundTasks` | No revelar qué emails existen, tampoco por el tiempo de respuesta (medianas con pausas: 51 ms existe / 47 ms no existe). Un fallo de Resend no cambia la respuesta. |
| El mensaje del backoffice es **fijo en el frontend** | La pantalla no puede revelar nada aunque cambie la respuesta de la API. |
| Token **opaco** (`secrets.token_urlsafe(32)`, 256 bits), no un JWT; en TinyDB solo su **SHA-256** | Un JWT con `exp` no se puede invalidar. SHA-256 basta para un valor aleatorio de 256 bits (bcrypt es para contraseñas) y permite buscarlo. |
| 30 minutos (`RESET_TOKEN_EXPIRE_MINUTES`, 15–60), **un solo uso**, el último enlace anula los anteriores | Requisitos del ticket. |
| Uso atómico: comprobar el token, marcar `used_at` y cambiar la contraseña bajo `_auth_lock`; bcrypt antes, fuera del candado | Dos peticiones simultáneas con el mismo token no pueden pasar las dos (4 y 8 en paralelo: una sola gana). El candado es de proceso: **un solo worker**, como ya exigía TinyDB. |
| Comprobación rápida del token antes de bcrypt en `reset-password` | Un token inventado no gasta ~0,25 s de CPU (denegación de servicio barata). |
| 400 con **un único mensaje** para cualquier enlace no válido | No dar pistas sobre si caducó, se usó o no existe. |
| Límite silencioso: 1 enlace por usuario cada 60 s (sigue el 200) | Que la API no sirva para inundar la bandeja de nadie. Usuarios desactivados: nunca reciben enlace. |
| **`password_changed_at`**: `get_current_user` rechaza los JWT con `iat` anterior (margen de 1 s) | Restablecer o cambiar la contraseña **cierra todas las sesiones abiertas**, también la de quien hubiera robado un token. `change-password` devuelve un token nuevo para que la sesión desde la que se cambia continúe. |
| `change-password` responde **400** (no 401) si la contraseña actual es incorrecta | El backoffice cierra la sesión ante un 401; aquí la sesión es válida. |
| `PUT /users/{id}` ya **no** admite `password` (422) | Antes un token robado bastaba para cambiar la contraseña sin la actual (decisión D1). |
| Cambiar el **email** con `PUT /users/{id}` exige `current_password` y anula los enlaces pendientes | Con la recuperación por email, cambiar el email con solo un token permitía quedarse con la cuenta: token robado → email del atacante → pedir enlace → nueva contraseña. Detectado en la fase 7 y cerrado (decisión D7). |
| Logs sin token, enlace, clave, destinatario ni mensaje de error de Resend | Solo propósito, id de usuario y tipo de error (`validation_error 403`…). |

### Email (Resend)

- `app/services/email.py`: interfaz `EmailSender` y dependencia `get_email_sender`. `ResendSender` llama a
  `POST https://api.resend.com/emails` con `urllib` (sin dependencias nuevas), `Idempotency-Key` (`password-reset/<id>`),
  `User-Agent` propio y 10 s de timeout. Sin `RESEND_API_KEY` se usa `DisabledSender` (no envía y avisa). Los tests
  sustituyen el emisor por uno falso: **ningún test envía emails**.
- `app/email_templates.py`: HTML con tablas y estilos en línea, 600 px que se adaptan al móvil, sin imágenes externas,
  URL escapada con `html.escape`, más versión de texto plano. Revisado a 900, 390 y 320 px.
- **Dominio propio:** `rubenlosada.com` verificado en Resend (registros `send` MX/TXT y `resend._domainkey` TXT en
  Cloudflare, *DNS only*). No afectan al correo de Hostinger de la raíz. Sin dominio, Resend solo entrega al titular de
  la cuenta. Clave de solo envío; remitente `TrackFlow <no-reply@rubenlosada.com>`.

### Backoffice

| Ruta | Acceso | Qué hace |
| --- | --- | --- |
| `/forgot-password` | pública | Email → «Revisa tu correo» con el mensaje genérico. Sin envíos dobles; errores sin datos del email. |
| `/reset-password?token=…` | pública | Dinámica (lee el token en el servidor) con `referrer: no-referrer`. Sin token: «Falta el enlace». Nueva + confirmación (deben coincidir; sin llamar a la API si no). 400 → «Este enlace ya no sirve» + «Volver a recuperar contraseña». Éxito → borra la sesión local y `router.replace` a `/login?motivo=restablecida` (aviso verde; el token sale del historial). |
| `/login` | pública | Enlace «¿Olvidaste tu contraseña?» bajo el campo de contraseña (orden del tabulador: email → contraseña → enlace → botón). |
| `/account/change-password` | **privada** | Actual + nueva + confirmación. 400 en «Contraseña actual»; 401 lo gestiona `lib/http.ts` (login). `AuthProvider.changePassword` guarda el token nuevo y **reprograma el temporizador de caducidad** (`tokenVersion`): sin eso la sesión se cerraba al caducar el token antiguo. Acceso desde la tarjeta «Seguridad» de Mi perfil. |

Reglas de email y contraseña compartidas en `lib/authRules.ts` (las mismas que la API) y `FieldError` en `AuthShell`.

### Verificación AUTH-03

- **API:** `uv run pytest -q -W error::DeprecationWarning` → **473 passed** (287 anteriores + 186: persistencia,
  email, los tres endpoints, revocación de sesiones y cambio de email). Pruebas de mutación en cada pieza crítica (uso
  único, caducidad, atomicidad, escapado del HTML, filtrado de errores del proveedor, enumeración, revocación, filtro
  previo a bcrypt, contraseña actual, cambio de email): todas detectadas.
- **Servidor real** (`uvicorn` con el `.env` real y TinyDB temporal): envíos reales a `delivered…@resend.dev`
  (`last_event: delivered`), `forgot-password` 10 respuestas idénticas, `reset-password` 10/10, `change-password` 13/13,
  cambio de email 6/6.
- **Navegador** (Edge + `playwright-core`, copia aislada del backoffice en `:3003`): `/forgot-password` 39/39,
  `/reset-password` 51/51, enlace del login 26/26, `/account/change-password` 42/42 (con tokens de 1 minuto para probar
  la caducidad), y **flujos A–F de punta a punta 33/33** con el enlace real del email capturado al enviarlo.
- **Regresión de AUTH-02** con sus baterías originales: 23 + 29 + 42 + 4 + 38 + 28 y 48/50 en protección de rutas
  (los 2 fallos son de la landing estática: `serve` redirige `application.html` → `application`; ni login, ni
  almacenamiento, ni llamadas a la API; `uis/landing` sin cambios).
- **Calidad:** `lint`, `typecheck` y `build` del backoffice; 7 rutas con `check-route.mjs`; 0 avisos de hidratación en
  `next dev`; `uv lock --check`; tests de `scripts` y del paquete (70).
- **Seguridad:** sin `.env` versionados; ninguna clave en código, historial, logs ni bundle del frontend; tokens solo
  como SHA-256 y contraseñas como bcrypt en la base.

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

## Verificación AUTH-02 (2026-10-01)

API de pruebas en `:8001` (`.env` y TinyDB en un directorio temporal, fuera del repo), backoffice con `npm run start`
y Edge sin interfaz con `playwright-core`, también fuera del repo.

### Tests automáticos

`uv run pytest -q -W error::DeprecationWarning` en `services/api` → **287 passed** (269 anteriores + 18 del código de
invitación: registro abierto sin la variable, código ausente, vacío, erróneo, en mayúsculas, recortado o no ASCII →
403 sin crear el usuario, código correcto con espacios → 201, el código no se guarda, 403 antes que 409, más de 200
caracteres → 422, `REGISTRATION_CODE` corto → la API no arranca, vacío → registro abierto). Prueba de mutación: sin la
comprobación en el router fallan 8 tests.

### E2E en el navegador (AUTH-02)

| Bloque | Resultado | Casos |
| --- | --- | --- |
| Sesión y cliente HTTP | 23/23 | token en `localStorage` (nada en `sessionStorage`, ninguna cookie), Bearer en `/suppliers`, recarga, pestañas (logout y login se propagan), token borrado → 401 → login, token manipulado, sin bucles |
| Login | 29/29 | vacío sin petición, credenciales incorrectas, cuenta desactivada (403), API caída, login sin `Authorization`, `next` (también `//evil.example`), 390 px |
| Registro con `REGISTRATION_CODE` | 42/42 | errores de cliente sin petición, 403 en el campo del código, 422 de la API traducidos (teléfono, nombre de 101 caracteres), mensaje desconocido mostrado tal cual, 500, API caída, alta → login automático → `/`, TinyDB sin código, 409 con enlace, `next`, alta correcta con login fallido, 390 px |
| Registro abierto (sin `REGISTRATION_CODE`) | 4/4 | solo se envían `email` y `password`; login automático |
| Protección de rutas | 50/50 | HTML del servidor sin panel, sin token → `/login?next=`, con token → acceso, token borrado (navegando, al volver a la pestaña, en una petición, desde otra pestaña), 401 por firma, token que caduca en mitad de la sesión, token caducado al cargar, usuario desactivado; website y landing: 200, sin redirección, **0 accesos a `localStorage`/`sessionStorage`**, sin llamadas a la API |
| Perfil | 38/38 | privada, `GET /auth/me` con Bearer, email/rol solo lectura, `PUT /profiles/me` con el cuerpo exacto, acentos, vaciar → `null`, 422 traducido sin guardar, descartar, API caída + reintentar, 401 al guardar, 390 px |
| Logout y ciclo completo | 28/28 | login → API (proveedores, análisis y descarga de incidencias) → logout → ruta privada → login sin ver el panel ni llamar a la API; «atrás» y recarga tras el logout; otro usuario sin restos del anterior; cuenta desactivada en mitad de la sesión → 401 → logout automático; «Salir» en móvil; **las 16 llamadas protegidas llevan Bearer** y las de login no |

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

1. **Registro + permisos amplios.** Cualquier usuario autenticado puede editar proveedores y subir CSV. Desde AUTH-02,
   **`REGISTRATION_CODE` limita quién puede registrarse: definirlo antes de publicar** (sin él, cualquiera crea una
   cuenta). Sigue abierta la opción de exigir `admin`/`manager` en las escrituras de proveedores e incidencias.
2. **Sin límite de intentos** de login ni de código de invitación (fuerza bruta): añadirlo en el proxy o en la API
   antes de publicar. Mientras tanto, el código exige al menos 12 caracteres.
3. **El registro revela si un email existe** (409) a quien tiene el código. Es inherente a detectar duplicados; sin
   código la respuesta es siempre 403.
4. **Token en `localStorage`** (requisito de AUTH-02): un XSS podría leerlo, igual que antes con `sessionStorage`, y
   ahora la sesión sobrevive a cerrar el navegador hasta el `exp` del token (30 min por defecto). Se mitiga con React,
   que escapa el contenido, y porque el backoffice no usa `dangerouslySetInnerHTML`. Sin *refresh tokens*: al caducar
   hay que volver a entrar.
5. **Despliegue:** ver [`docs/despliegue-api.md`](./despliegue-api.md). Desplegar este backoffice **sin** la API
   publicada deja el panel inaccesible, porque el login necesita la API.
6. **Los 422 de FastAPI devuelven el valor recibido** (`input`), también la contraseña cuando no cumple las reglas. Va
   solo a quien la envió y el backoffice no lo muestra ni lo registra, pero un proxy que guarde cuerpos de respuesta
   la vería. Comportamiento por defecto de FastAPI; cambiarlo requiere un manejador de errores propio. Afecta también a
   `new_password` en `reset-password` y `change-password` (AUTH-03).
7. **AUTH-03 — sin límite por IP** en `forgot-password` (solo 1 enlace por usuario cada 60 s) ni de intentos en
   `change-password`: mismo pendiente que el login (proxy o API antes de publicar).
8. **AUTH-03 — un solo worker:** el uso único del enlace se garantiza con un candado de proceso.
9. **AUTH-03 — señal de tiempo residual:** una petición que llega mientras otro email se envía en segundo plano puede
   tardar unos milisegundos más. Señal débil y con mucho ruido.
10. **AUTH-03 — margen de 1 s:** un JWT emitido en el mismo segundo que el cambio de contraseña sigue valiendo (`iat`
    va en segundos enteros).

## Ficheros

```text
services/api/
├── .env.example              # SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REGISTRATION_CODE, RESEND_API_KEY, MAIL_FROM… (sin valores)
├── app/
│   ├── auth_models.py        # Role, User, Profile, PasswordResetToken y schemas de entrada/salida
│   ├── security.py           # configuración, bcrypt, JWT, código de invitación, token y enlace de recuperación
│   ├── dependencies.py       # OAuth2PasswordBearer + get_current_user (+ revocación por password_changed_at)
│   ├── create_admin.py       # `uv run create-admin <email>`
│   ├── database.py           # + auth_db() (TinyDB de usuarios, candado propio)
│   ├── email_templates.py    # AUTH-03: email de recuperación (HTML + texto)
│   ├── services/users.py     # CRUD de usuarios (alta y baja junto con el perfil) y change_password
│   ├── services/profiles.py  # CRUD de perfiles
│   ├── services/password_reset.py  # AUTH-03: emitir, consultar, usar (atómico) y revocar enlaces
│   ├── services/email.py     # AUTH-03: EmailSender, ResendSender, DisabledSender y deliver
│   └── routes/auth.py · users.py · profiles.py
└── tests/test_auth.py · test_password_reset.py · test_email.py

uis/backoffice/
├── app/login/page.tsx        # /login
├── app/register/page.tsx     # /register
├── app/(panel)/layout.tsx    # panel protegido (AuthGate + sidebar + barra superior)
├── app/(panel)/account/profile/page.tsx  # /account/profile (+ tarjeta «Seguridad»)
├── app/(panel)/account/change-password/page.tsx  # AUTH-03: /account/change-password
├── app/forgot-password/page.tsx  # AUTH-03: /forgot-password
├── app/reset-password/page.tsx   # AUTH-03: /reset-password?token=…
├── components/auth/          # AuthProvider, AuthGate, AuthShell, LoginScreen, RegisterScreen, ProfileEditor,
│                             # SidebarAccount, UserMenu, LogoutIcon, ForgotPasswordScreen, ResetPasswordScreen,
│                             # ChangePasswordForm
├── lib/session.ts            # token en localStorage, caducidad, `next` seguro
├── lib/auth.ts               # /auth/login, /users, /auth/me, /profiles/me, recuperación y cambio de contraseña
├── lib/authRules.ts          # AUTH-03: reglas de email y contraseña (las mismas que la API)
├── lib/authErrors.ts         # errores de la API en español para los formularios de cuenta
└── lib/http.ts               # Authorization: Bearer en las peticiones protegidas y cierre de sesión ante 401
```
