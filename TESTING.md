# TESTING — Pruebas unitarias de TrackFlow

> **Estado (2026-10-20): AUTH-088, API-042 y FE-019 implementados y validados** en la rama `feature/auth-088-tests`.
> Todas las cifras de este documento salen de ejecuciones reales; los comandos están en la sección 2 y el detalle de
> cada medición, en la sección 12.

## 1. Tickets y estado

| Ticket | Prioridad | Objetivo | Estado |
| --- | --- | --- | --- |
| **AUTH-088** — Cobertura de pruebas unitarias para la API de autenticación | Alta | Un módulo por endpoint con casos de camino feliz, límite y fallo; ≥ 70 % de cobertura del código de autenticación; Jest para las utilidades TS de autenticación | ✅ 12 endpoints, 13 módulos (165 tests), **100 %** del ámbito con la suite completa (97 % solo con la nueva); Jest: 4 suites (59 tests); 2 defectos reales corregidos |
| **API-042** — Dos grupos de endpoints del backoffice | Baja | ≥ 60 % de cobertura en los módulos probados | ✅ Proveedores (6 endpoints) y gestor de incidencias (5): 11 módulos (88 tests), **100 %** de los 5 módulos con la suite completa (97 % solo con la nueva) |
| **FE-019** — Utilidades del frontend con Jest | Baja | Tres funciones reales con casos de éxito y fallo | ✅ 5 funciones de `lib/suppliers.ts` y `lib/incidents.ts`: 2 suites (32 tests) |

La autenticación ya estaba implementada (AUTH-01 a AUTH-03): estas pruebas no la reescriben, verifican su
comportamiento. Los tests HTTP existentes (`tests/test_auth.py`, `tests/test_password_reset.py`, `tests/test_api.py`,
`tests/test_incident_manager.py`…) no se han modificado y siguen siendo la red de regresión.

## 2. Cómo instalar y ejecutar

Un comando por línea (Windows PowerShell 5.1).

**Backend** (desde `services\api`):

```powershell
uv sync
uv run pytest
uv run pytest tests/auth
uv run pytest tests/backoffice
```

- `uv sync` instala también el grupo `dev` (pytest, pytest-cov, httpx2).
- No hace falta `.env`: `tests/conftest.py` fija una `SECRET_KEY` de pruebas, apunta las tres bases TinyDB a
  ficheros temporales y elimina `RESEND_API_KEY` (ningún test envía emails). `tests/auth/conftest.py` además bloquea
  cualquier conexión de red.

**Cobertura** (desde `services\api`):

```powershell
uv run pytest --cov=app.security --cov=app.dependencies --cov=app.routes.auth --cov=app.routes.users --cov=app.services.password_reset --cov=app.services.users --cov=app.auth_models --cov-branch --cov-report=term-missing
uv run pytest --cov=app.routes.suppliers --cov=app.models --cov=app.routes.incident_manager --cov=app.services.incidents --cov=app.incident_models --cov-branch --cov-report=term-missing
uv run pytest --cov --cov-branch --cov-report=term-missing
```

La primera mide el ámbito de AUTH-088, la segunda el de API-042 y la tercera toda la API (`[tool.coverage.run]
source = ["app"]` en `pyproject.toml`). **La cifra global no es la de autenticación**: se informan por separado. Para
medir solo una suite nueva, añade su carpeta (`tests/auth` o `tests/backoffice`) al comando.

**Frontend** (desde `uis\backoffice`):

```powershell
npm install
npm test
npm run test:coverage
```

Jest 30 con `next/jest` (`jest.config.mjs`): compila TypeScript con SWC y resuelve el alias `@/`. Entorno `node`, sin
jsdom. Los tests viven junto al código (`lib/*.test.ts`).

## 3. Línea base (2026-10-19, antes de escribir pruebas nuevas)

| Suite | Comando | Resultado |
| --- | --- | --- |
| API (`services/api`) | `uv run pytest -q` | 789 passed en 203 s |
| Scripts y paquete del analizador (raíz) | `python -m pytest scripts/tests packages/analisis-incidencias/tests -q` | 196 passed en 0,7 s |
| Frontend | — | No había tests ni Jest |

Cobertura de **líneas** del ámbito de autenticación con la suite existente: **99 %** (531 sentencias, 2 sin cubrir:
`app/routes/auth.py:170`, usuario borrado durante el cambio de contraseña, y `app/services/users.py:94`). El umbral del
70 % ya se cumplía; el valor de AUTH-088 está en organizar la suite por endpoint, probar las decisiones de negocio a
nivel unitario, fijar los casos límite con precisión (instantes exactos, longitudes en bytes, márgenes de 1 s) y cubrir
las ramas que faltaban. Así salieron a la luz los dos defectos de la sección 11.

## 4. Inventario de endpoints de autenticación

| # | Endpoint | Función productiva | Módulo de tests |
| --- | --- | --- | --- |
| 1 | `POST /users` (registro público) | `routes/users.py` `register` → `services/users.create_user` | `tests/auth/test_register.py` |
| 2 | `POST /auth/login` | `routes/auth.py` `login`, `authenticate` | `tests/auth/test_login.py` |
| 3 | `POST /auth/token` (formulario OAuth2 de Swagger) | `routes/auth.py` `login_form` | `tests/auth/test_token_form.py` |
| 4 | Validación del Bearer token (dependencia de toda ruta protegida) | `dependencies.py` `get_current_user`, `issued_after_password_change`; `security.py` | `tests/auth/test_token.py` |
| 5 | `GET /auth/me` | `routes/auth.py` `me` | `tests/auth/test_me.py` |
| 6 | `POST /auth/forgot-password` | `routes/auth.py` `forgot_password` → `services/password_reset.issue_reset_token` | `tests/auth/test_forgot_password.py` |
| 7 | `POST /auth/reset-password` | `routes/auth.py` `reset_password` → `consume_reset_token` | `tests/auth/test_reset_password.py` |
| 8 | `POST /auth/change-password` | `routes/auth.py` `change_password` | `tests/auth/test_change_password.py` |
| 9 | `GET /users` | `routes/users.py` `list_users` | `tests/auth/test_users_list.py` |
| 10 | `GET /users/{id}` | `routes/users.py` `get_user` | `tests/auth/test_users_get.py` |
| 11 | `PUT /users/{id}` | `routes/users.py` `update_user` | `tests/auth/test_users_update.py` |
| 12 | `DELETE /users/{id}` | `routes/users.py` `delete_user` | `tests/auth/test_users_delete.py` |

Los endpoints 9–12 son de **autorización** (rol y propiedad); `app/routes/users.py` se mide entero. `/profiles/me`
queda fuera: no decide nada de autenticación. **No existen** y no se han implementado: refresh tokens, logout en
servidor (JWT sin estado), bloqueo por intentos ni límite de intentos de login.

`tests/auth/test_fixtures.py` (5 tests) no prueba la aplicación: vigila la propia infraestructura (sección 5).

## 5. Enfoque

- **Real:** bcrypt, la firma JWT, TinyDB (fichero temporal por test) y las funciones de router y de servicio, que se
  llaman directamente (`authenticate(...)`, `register(payload)`, `get_current_user(token)`, `change_password(...)`,
  `create_supplier(payload, table)`, `update_status(...)`) comprobando sus resultados y las `HTTPException` del
  contrato.
- **Aislado:** el email (emisor falso), el reloj, las variables de entorno y la red.
- **Reloj:** fixture `clock` que congela `datetime.now` en `app.security`, `app.services.users`,
  `app.services.password_reset` y `jose.jwt` (backoffice: `app.models.utc_now`). Sin dependencias nuevas. Como depende
  de un detalle interno de python-jose, `test_fixtures.py` comprueba que el token es válido 1 s antes de `exp` y está
  caducado 1 s después: si una versión nueva de jose dejara de leer el reloj congelado, ese test fallaría.
- **Espías, no mocks de la lógica:** `create_access_token`, `burn_password_check` y `hash_password` se envuelven con
  una función que **llama a la real** y solo cuenta las llamadas (¿se emitió un token?, ¿se gastó un bcrypt?).
- **`TestClient` solo para el cableado:** 3 tests comprueban que una ruta concreta exige el Bearer
  (`/auth/me` ×2, `/api/incidents/summary`); eso no se ve llamando a la función.
- **Pruebas de mutación** en cada fase (sección 13): cambiar el código, ver fallar el test, restaurar.
- Datos sintéticos (`*@trackflow.test`), contraseñas de prueba y una `SECRET_KEY` de pruebas que no es secreta.

## 6. Casos por endpoint de autenticación (implementados)

| Endpoint | Camino feliz | Caso límite | Modo de fallo | Comportamiento de negocio verificado |
| --- | --- | --- | --- | --- |
| **1. `POST /users`** (20 tests) | Alta con rol `user`, activa, perfil 1:1; solo se guarda el hash bcrypt (`$2b$12$`), que verifica | Contraseñas de 8 caracteres y de 72 bytes (36 «ñ») aceptadas **y sirven para entrar**; 7 y 73 bytes rechazadas; email normalizado; perfil en blanco → `null`; **contraseña con espacios en los extremos (D-1)** | Email duplicado aunque cambien las mayúsculas → 409 sin tocar el original; código de invitación ausente, vacío, incorrecto o con otras mayúsculas → 403 sin crear nada; `role`/`is_active`/`id` en el cuerpo → rechazados | Nadie se registra como admin; el código se comprueba antes que el email y nunca se guarda |
| **2. `POST /auth/login`** (11) | Token `bearer` con `sub` = id, 1800 s y `exp` = T0 + 30 min | Email con espacios y mayúsculas; campos vacíos → 401; 73 bytes → 401 (no 500); contraseña sensible a mayúsculas | Contraseña incorrecta y email inexistente → **mismo** 401, mensaje y cabecera; el email inexistente gasta igualmente un bcrypt; desactivada + contraseña correcta → 403, + incorrecta → 401 | Ningún fallo emite token; no se revela si el email existe ni si la cuenta está desactivada |
| **3. `POST /auth/token`** (6) | Token equivalente al del login JSON | `username` con mayúsculas o espacios → normalizado | 401 con `WWW-Authenticate: Bearer`; desactivada → 403 | El router normaliza el email (el formulario no pasa por `LoginRequest`) |
| **4. Validación del token** (35) | Token recién emitido → usuario activo | **Instante exacto de `exp` (D-2)**; `exp` en texto; token del mismo segundo que un cambio de contraseña válido, 1 s antes revocado; `ACCESS_TOKEN_EXPIRE_MINUTES=1`; `SECRET_KEY` de 32 caracteres | Sin token, malformado, otra clave, `alg: none`, HS512, caducado (mensaje propio), sin `sub`/`exp`, `sub` vacío o numérico, id inexistente, `iat` ausente o booleano tras un cambio, usuario desactivado o borrado → 401; `SECRET_KEY` vacía, de ejemplo o de 31 caracteres y duraciones inválidas → `ConfigError` | Solo un token íntegro, vigente, de un usuario activo y posterior al último cambio de contraseña da acceso |
| **5. `GET /auth/me`** (5) | Cuenta y perfil sin credenciales | Perfil ausente → se crea una vez (1:1) | Sin token o de un usuario desactivado → 401 (cableado) | El rol sale de la base en cada petición, no del token |
| **6. `POST /auth/forgot-password`** (19) | Enlace guardado solo como SHA-256, email **después** de responder, URL del backoffice, caducidad 30 min, clave de idempotencia | 59 s → sin enlace nuevo; **60 s exactos** → enlace nuevo que anula el anterior; email normalizado; `FRONTEND_BASE_URL` con barra final; validez de 15 y 60 min | Email inexistente o desactivado → misma respuesta sin enlace ni email; proveedor caído → misma respuesta y log sin email ni token; email mal formado; validez de 14/61 min y URL no válida → `ConfigError` | La respuesta nunca revela si el email existe |
| **7. `POST /auth/reset-password`** (15) | Cambia la contraseña, marca el enlace como usado y cierra las sesiones | Válido 1 µs antes de `expires_at`, **caducado en `expires_at`**; contraseña nueva de 8, 72 bytes o con espacios, tal cual | Reutilizado, manipulado, inventado, vacío, de una solicitud anterior o de un usuario desactivado → mismo 400 sin cambios; contraseña inválida no consume el enlace; enlace inválido no gasta bcrypt | Un solo uso, con caducidad; no inicia sesión |
| **8. `POST /auth/change-password`** (14) | Token nuevo válido; las demás sesiones y los enlaces pendientes quedan anulados | Nueva igual a la actual → rechazo; token nuevo del mismo segundo válido; contraseñas límite tal cual | Actual incorrecta (4 variantes) → 400 sin cambios; **usuario borrado durante el cambio → 401** (la línea que faltaba); solo afecta al titular | Exige la contraseña actual y cierra la sesión de un posible token robado |
| **9. `GET /users`** (5) | Admin y manager listan por fecha de alta, sin hashes | Lista de un solo usuario | `user` → 403; manager degradado pierde el acceso con el mismo token | Solo el staff ve usuarios ajenos |
| **10. `GET /users/{id}`** (6) | Registro propio; staff ve a otros | Staff con id inexistente → 404; `user` → **403, no 404** | `user` sobre otro → 403 | No se pueden averiguar ids sin ser staff |
| **11. `PUT /users/{id}`** (19) | Cambio del propio email con contraseña (anula enlaces); admin cambia rol y estado | Email igual salvo mayúsculas; desactivar cierra la sesión al momento | Sin contraseña o incorrecta → 400; `user` cambia su rol → 403; admin cambia un email ajeno → 403; manager/`user` sobre otro → 403; permisos antes que contraseña; email ocupado → 409; id inexistente → 404; cuerpo vacío, solo `current_password`, `password`, `role` null o inexistente → rechazado | Un token robado no basta para desviar la recuperación de la cuenta |
| **12. `DELETE /users/{id}`** (5) | Baja propia: usuario y perfil borrados, la sesión muere | Admin borra a otro; repetir → 404 | Manager/`user` sobre otro → 403; `user` con id inexistente → 403 | Solo el propio usuario o un admin |

## 7. Casos de seguridad verificados

- **Contraseñas:** solo hash bcrypt; nunca en respuestas, base ni logs; se comparan tal cual se escriben (D-1).
- **Enumeración:** mismo 401 y mismo coste bcrypt; misma respuesta en `forgot-password`; 403 antes que 404; código de
  invitación antes que el email duplicado; permisos antes que la contraseña.
- **Tokens:** firma, algoritmo fijo, caducidad estricta (D-2), claims, revocación por cambio de contraseña,
  desactivación o borrado.
- **Enlaces de recuperación:** SHA-256, un solo uso, caducidad, revocados al cambiar contraseña o email, sin token en
  los logs.
- **Escalada de privilegios:** el registro no admite `role`; solo un admin cambia roles; nadie cambia el email ajeno.
- **Aislamiento:** ningún test usa `db/*.json` reales, credenciales reales, Resend ni la red (`block_network`).

## 8. Caso límite adicional de la revisión asistida por IA

**Instante exacto de caducidad del JWT.** Al leer `jose/jwt.py` (`_validate_exp`) durante la Fase 2 se vio que
python-jose solo rechaza un token si `exp < ahora` (segundos enteros): el token seguía valiendo durante el segundo
exacto de `exp`, mientras que los enlaces de recuperación de la propia API caducan en el instante
(`now >= expires_at`) y RFC 7519 §4.1.4 exige que la hora actual sea **anterior** a `exp`.

- Implementado en `tests/auth/test_token.py::test_token_expires_exactly_at_its_exp_instant`: token de 60 s válido a
  los 59,999999 s y caducado a los 60 s y a los 61 s (reloj congelado).
- Con el código original **fallaba** (junto con `test_token_lifetime_follows_access_token_expire_minutes`). El
  desarrollador decidió tratarlo como defecto (opción A): D-2, sección 11.
- Su homólogo en los enlaces de recuperación (`test_reset_password.py::test_link_is_expired_exactly_at_expires_at`)
  confirma que ahora ambos criterios coinciden.

## 9. Utilidades TypeScript de autenticación (AUTH-088, Jest)

| Fichero de test | Funciones | Éxito | Límite | Fallo |
| --- | --- | --- | --- | --- |
| `lib/session.test.ts` (27) | `tokenExpiry`, `safeNextPath`, `readToken`/`saveToken`/`clearToken` | `exp × 1000`; rutas internas permitidas; guardar, leer y borrar | base64url con `-`/`_` y sin relleno; `/loginx` permitido y `/login/` no; sin `window` (servidor) | token sin partes, no JSON, `exp` en texto o ausente → `null`; `//otro`, `/\otro`, `https://…`, pantallas de acceso → `/`; `localStorage` bloqueado → sin sesión y sin lanzar |
| `lib/authRules.test.ts` (11) | `passwordProblem`, `EMAIL_PATTERN` | 8 caracteres; emails válidos | 72 bytes con «ñ»; espacios en los extremos | 7 caracteres; 73 bytes con 37 caracteres; emails sin dominio, con espacio o doble `@` |
| `lib/authErrors.test.ts` (12) | `translateApiMessage`, `toFormErrors` | 401 técnicos → «sesión caducada»; errores repartidos por campo | campo no visible → al mensaje general con su etiqueta; sin punto final → se añade | 5xx sin detalle del servidor; error que no es `ApiError` → mensaje genérico |
| `lib/auth.test.ts` (9) | `displayName`, `initials` | «Laura Gómez» → «LG» | nombre vacío o en blanco → parte local del email; separadores `.`/`_`; tildes y «ñ» | email sin separadores → dos letras |

Se ejercitan las funciones reales; solo se simula `window.localStorage`. `authApi` (envoltorio de `fetch`) queda fuera:
no tiene lógica propia que probar sin simular la red.

## 10. API-042 y FE-019

### API-042 — Backend del backoffice

Grupos elegidos por concentrar reglas de negocio del CONTEXT (`CONTEXT-directorio.md`,
`CONTEXT-gestor-incidencias.es.md`). Módulos medidos: `app/routes/suppliers.py`, `app/models.py`,
`app/routes/incident_manager.py`, `app/services/incidents.py` y `app/incident_models.py`. Tests en
`services/api/tests/backoffice/`, llamando a las funciones del router con la tabla TinyDB real temporal.

| Endpoint (módulo) | Camino feliz | Caso límite | Modo de fallo |
| --- | --- | --- | --- |
| `POST /suppliers` (`test_suppliers_create.py`, 16) | Id y `updated_at` del servidor | Tarifa 0,01; textos recortados; categorías sin repetidas en su orden; opcionales vacíos → `null` | Moneda incoherente con el país; tarifa 0, negativa, texto, booleano, ∞ o NaN; nombre vacío, sin categorías, categoría o país fuera del CONTEXT, email mal formado → nada se guarda |
| `GET /suppliers` (`test_suppliers_list.py`, 8) | Todos; filtro por país | Proveedor con varias categorías; filtros con AND; sin coincidencias; directorio vacío | Valores de filtro fuera del CONTEXT |
| `GET /suppliers/{id}` (`test_suppliers_get.py`, 5) | Devuelve el proveedor | Cada id, el suyo | 99, 0 y -1 → 404 con el id |
| `PATCH /suppliers/{id}/rate` (`test_suppliers_rate.py`, 8) | Renueva `updated_at` y no toca nada más | Tarifa 0,01 | Tarifa inválida; proveedor inexistente → 404 sin crear nada |
| `PATCH /suppliers/{id}/status` (`test_suppliers_status.py`, 6) | Suspender **no** cambia `updated_at` (es la fecha de la tarifa) | Reactivar y repetir el mismo estado | Estados fuera de `active`/`suspended`; inexistente → 404 |
| `DELETE /suppliers/{id}` (`test_suppliers_delete.py`, 4) | Desaparece | Los demás quedan intactos | Inexistente y segundo borrado → 404 |
| `POST /api/incidents` (`test_incidents_create.py`, 15) | Nace `open` con fechas del servidor y textos recortados; el cliente no elige estado, fechas ni id | Título 120 y descripción 2000 aceptados; 121/2001 rechazados | Obligatorios, valores fuera de lista y tipos con el mensaje compartido en español; el 400 por campo no devuelve el valor recibido; errores del framework traducidos |
| `GET /api/incidents` (`test_incidents_list.py`, 7) | De más reciente a más antigua; filtros con AND | Misma fecha → por id descendente; sin coincidencias; base vacía | Filtros fuera del CONTEXT |
| `GET /api/incidents/summary` (`test_incidents_summary.py`, 3) | Totales por estado, categoría, origen y sede | Base vacía → **todas** las claves a 0 | Sin sesión → 401 (cableado) |
| `GET /api/incidents/{id}` (`test_incidents_get.py`, 5) | Devuelve la incidencia | Cada id, la suya | 99, 0 y -1 → 404 con el id |
| `PATCH /api/incidents/{id}/status` (`test_incidents_status.py`, 11) | `open → in_progress → resolved` renueva `updated_at` | Descartar desde los dos estados no finales | Estados finales; saltarse `in_progress` (con el motivo exacto); mismo estado; inexistente → 404; estado desconocido |

### FE-019 — Utilidades del frontend

| Fichero de test | Funciones | Éxito | Fallo |
| --- | --- | --- | --- |
| `lib/suppliers.test.ts` (26) | `parseRate`, `validateDraft`, `formatRate`, `formatDateTime` | Coma o punto decimal; payload con la moneda del país (EUR/USD) y opcionales a `null`; formato es-ES con 2–4 decimales | `""`, `0`, negativa, texto, `7,4,5`, ∞ → `null`; errores con la clave de la API y sin payload; moneda que `Intl` no reconoce → texto sin formato; fecha inválida → «Fecha no disponible» |
| `lib/incidents.test.ts` (6) | `validateIncidentDraft` | Payload con textos recortados; 120 y 2000 caracteres tras recortar | 121 / 2001 caracteres, título en blanco, borrador vacío (los cinco campos) |

Se descartó `etiquetaSemana` (`lib/formato.ts`): no define qué hacer con una clave mal formada y no se inventa ese
contrato.

## 11. Defectos encontrados

| Id | Dónde | Defecto | Consecuencia | Test que lo demuestra | Estado |
| --- | --- | --- | --- | --- | --- |
| D-1 | `app/auth_models.py` `UserCreate` | Heredaba de `ProfileFields` `str_strip_whitespace: True`, que también recortaba la **contraseña** al registrarse; `LoginRequest`, `ResetPasswordRequest` y `ChangePasswordRequest` no recortan, y el backoffice la envía tal cual | Quien se registraba con una contraseña con espacios en los extremos recibía 401 al entrar escribiendo exactamente esa contraseña; la longitud mínima se medía sobre el texto recortado | `tests/auth/test_register.py::test_password_keeps_leading_and_trailing_spaces` (fallaba con 401) | **Corregido** (opción A aprobada): `password: Annotated[str, StringConstraints(strip_whitespace=False)]`. El resto de campos se sigue recortando; los hashes ya guardados no cambian |
| D-2 | `app/security.py` `decode_access_token` | python-jose solo rechaza `exp < ahora`: el token valía durante el segundo exacto de `exp` | Ventana de hasta 1 s en la que un token caducado daba acceso | `tests/auth/test_token.py::test_token_expires_exactly_at_its_exp_instant` y `::test_token_lifetime_follows_access_token_expire_minutes` (fallaban con `DID NOT RAISE`) | **Corregido** (opción A aprobada): tras `jwt.decode`, `ExpiredSignatureError` si `int(exp) <= ahora`. `int()` como jose, para que un `exp` en texto no dé 500 (`::test_exp_written_as_text_is_compared_as_a_number`, que detecta su regresión) |

**Observaciones que no se han tratado como defectos** (sin contrato que lo defina o fuera del alcance):

- **Ids de proveedor reutilizados:** TinyDB asigna «máximo + 1» al reabrir la base, así que tras borrar el último
  proveedor el siguiente alta recibe su id (comprobado en una base temporal). No hay contrato sobre ids y el flujo de
  TrackFlow es suspender, no borrar; no se ha fijado con un test. Pendiente de decisión.
- **Filtro de `iat` booleano** en `issued_after_password_change`: una mutación que lo quita sobrevive porque `True`
  vale 1 (1970) y la comparación ya lo rechaza. Es defensivo; no se ha forzado un test artificial.
- **`npm audit` en `uis/backoffice`:** `next` 16.3.4 (también en el website) tiene un aviso *critical* (RCE en
  `next/og`) y varios *high*, ya presentes en `main`; **16.3.8** los corrige. Jest añade avisos *moderate* solo de
  desarrollo. No se ha tocado: requiere confirmación (ver `memory-bank/progress.md`).

## 12. Resultados (ejecuciones reales, 2026-10-20)

| Comando | Resultado |
| --- | --- |
| `uv run pytest -q -W error::DeprecationWarning --cov --cov-branch --cov-report=term-missing` (`services\api`) | **1042 passed** en 284 s (789 anteriores + 165 de `tests/auth` + 88 de `tests/backoffice`), sin avisos de deprecación |
| `uv run pytest tests/auth -q` con la cobertura de AUTH-088 | 165 passed en 67 s |
| Cada módulo de `tests/auth` por separado | Los 13 pasan aislados (sin dependencias de orden) |
| `uv run pytest tests/backoffice -q` | 88 passed en 1 s |
| `python -m pytest scripts/tests packages/analisis-incidencias/tests -q` (raíz) | 196 passed (sin cambios) |
| `npm test` / `npm run test:coverage` (`uis\backoffice`) | **91 passed**, 6 suites |
| `npm run lint`, `npm run typecheck`, `npm run build` (`uis\backoffice`) | Sin errores |

**Cobertura de líneas y ramas** (pytest-cov 7.1, `--cov-branch`):

| Ámbito | Con la suite completa | Solo con su suite nueva |
| --- | --- | --- |
| **AUTH-088**: `security`, `dependencies`, `routes/auth`, `routes/users`, `services/password_reset`, `services/users`, `auth_models` | **100 %** (534 sentencias, 132 ramas, 0 sin cubrir) | 97 % (`tests/auth`: faltan reglas de perfil, código de invitación corto, `check_auth_config` y la purga de enlaces antiguos, que cubren los tests anteriores) |
| **API-042**: `routes/suppliers`, `models`, `routes/incident_manager`, `services/incidents`, `incident_models` | **100 %** (249 sentencias, 30 ramas) | 97 % (`tests/backoffice`: falta el manejador HTTP de `IncidentRoute`, cubierto por `test_incident_manager.py`) |
| Toda la API (`app/`), referencia | 99 % (1230 sentencias, 218 ramas, 10 sin cubrir: `create_admin`, `errors`, `seed`, `profiles`) | — |

**Cobertura de Jest** (líneas / ramas, `npm run test:coverage`): `session.ts` 100 % / 100 %, `authRules.ts` 100 % /
100 %, `authErrors.ts` 100 % / 100 %, `auth.ts` 54 % (sin `authApi`), `suppliers.ts` 77 % / 82 % (sin `suppliersApi`),
`incidents.ts` 55 % / 53 % (sin `incidentsApi`, `formatIncidentDate` ni `incidentErrorMessage`). El total de `lib/`
(45 % de líneas) incluye ficheros que no forman parte de ningún ticket (`formato.ts`, `http.ts`, `initiatives.ts`…).

## 13. Pruebas de mutación

Cada fila: cambio temporal del código productivo → tests que fallan → fichero restaurado (`git diff` vacío).

| Mutación | Detectada por |
| --- | --- |
| Quitar `jose.jwt` del reloj congelado | `test_fixtures.py` (2 tests). **Detectó un falso positivo propio**: la primera versión pasaba igual con el reloj real |
| Quitar la verificación bcrypt de un email inexistente | `test_login.py::test_unknown_email_still_runs_a_bcrypt_check` |
| Mensaje distinto para email inexistente | 3 tests de `test_login.py` |
| Sin `normalize_email` en `/auth/token` | 2 tests de `test_token_form.py` |
| Sin comprobar `is_active` en `get_current_user` | `test_token.py::test_token_of_a_deactivated_user_is_invalid` |
| Quitar `int()` de la corrección de D-2 | 2 tests de `test_token.py` |
| Quitar el filtro de `iat` booleano | **Sobrevive** (sección 11) |
| `/auth/me` sin `Depends(get_current_user)` | 2 tests de `test_me.py` |
| Enlace de recuperación también a usuarios desactivados | `test_forgot_password.py` |
| Espera de 60 s con `<=` | `test_forgot_password.py::test_cooldown_blocks_a_second_link_until_exactly_60_seconds` |
| Enlace caducado con `>` en lugar de `>=` | `test_reset_password.py::test_link_is_expired_exactly_at_expires_at` |
| Sin la comprobación previa a bcrypt en el reset | `test_reset_password.py::test_invalid_link_is_rejected_before_spending_cpu_on_bcrypt` |
| Reset sin `password_changed_at` | `test_reset_password.py` (cierre de sesiones) |
| Cambio de contraseña sin revocar enlaces | `test_change_password.py` |
| 401 en lugar de 400 con la contraseña actual incorrecta | 4 tests de `test_change_password.py` |
| Rol `user` tratado como staff | 4 tests de `test_users_list.py` y `test_users_get.py` |
| Admin puede cambiar emails ajenos | `test_users_update.py` |
| Manager puede borrar usuarios | `test_users_delete.py` |
| Cambiar el estado de un proveedor renueva `updated_at` | `test_suppliers_status.py` |
| Filtro de categoría solo sobre la primera | 2 tests de `test_suppliers_list.py` |
| Orden de incidencias sin desempate por id | `test_incidents_list.py` |
| `safeNextPath` sin bloquear `/\` | `session.test.ts` |
| `parseRate` admite 0 | 2 tests de `suppliers.test.ts` |
| Límite del título con `>=` | `incidents.test.ts` |

## 14. Límites conocidos

- TinyDB y su candado de proceso exigen un único worker; los tests de concurrencia existentes usan hilos, no procesos.
- bcrypt es lento a propósito (~0,25 s por hash): la suite completa de la API tarda unos 5 minutos.
- El reloj congelado de los JWT parchea `datetime` dentro de `jose.jwt` (detalle interno); lo vigila
  `test_fixtures.py`.
- El test de tiempos del login comprueba que se ejecuta la verificación bcrypt ficticia, no que los tiempos midan
  igual (medirlos sería lento y frágil).
- Las pruebas de mutación se hicieron a mano (sin `mutmut`), una o varias por endpoint, no de forma exhaustiva.
- No hay CI: las suites se ejecutan con los comandos de la sección 2.
