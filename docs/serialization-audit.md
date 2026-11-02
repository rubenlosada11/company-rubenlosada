# Auditoría de serialización de la API (`services/api`)

Práctica sin número de hito. Rama `feature/serialization-audit` (2026-11-02). Este documento conserva el **estado
original** de cada endpoint (sección 5) y, a continuación, el diseño aprobado y el **estado final** tras las
correcciones (secciones 12–15). El estado original no se reescribe: es el punto de partida de la auditoría.

## 1. Objetivo y alcance

Llevar todos los endpoints de la API de TrackFlow a un contrato de respuesta explícito y revisado:

- que ninguna respuesta pueda exponer por accidente contraseñas, hashes, tokens internos o campos de control;
- que cada endpoint declare su `response_model` y que OpenAPI (`/docs`) refleje el contrato real;
- que los esquemas de salida no dependan de los de entrada ni de los modelos persistidos;
- que los payloads se ajusten a lo que consumen los clientes reales, sin N+1 ni relaciones innecesarias.

**Alcance:** la única aplicación FastAPI del monorepo, `services/api/` (todos sus routers) y los contratos que consume
`uis/backoffice`. Fuera de alcance: `uis/website` (no llama a la API), las apps de hitos anteriores, la lógica de
negocio, el mecanismo de autenticación y la estructura de las bases de datos.

## 2. Arquitectura inspeccionada

| Pieza | Ubicación | Notas |
| --- | --- | --- |
| App FastAPI | `services/api/app/main.py` | Un solo `FastAPI`, `default_response_class` JSON UTF-8, middleware de 500 genérico + CORS, manejador común de 422 sin valores recibidos, `/health` |
| Routers | `services/api/app/routes/` | `auth`, `users`, `profiles`, `suppliers`, `incidents` (analizador), `incident_manager` (con `IncidentRoute`: 400 por campo), `inventory` |
| Dependencias | `app/dependencies.py` | `get_current_user` (Bearer JWT, relee el usuario en cada petición) |
| Modelos persistidos | `app/auth_models.py` (`User`, `Profile`, `PasswordResetToken`), `app/incident_models.py` (`IncidentRecord`), `app/inventory_models.py` (`SKU`, `StockEntry`, `StockExit`, SQLModel) | Usuarios, perfiles, proveedores e incidencias en **TinyDB** (JSON); inventario en **SQL** (SQLite o PostgreSQL/Supabase) |
| Esquemas Pydantic | `app/auth_models.py`, `app/models.py` (proveedores), `app/incident_models.py`, `app/inventory_schemas.py` | Entrada y salida en el mismo módulo de cada dominio |
| Servicios | `app/services/` | `users`, `profiles`, `password_reset`, `email`, `incidents`, `inventory`. Sin capa de repositorio: los servicios acceden a TinyDB/SQL directamente |
| Analizador de CSV | paquete `packages/analisis-incidencias` | `analizar()` devuelve un `dict`; la API lo reenvía |
| Tests | `services/api/tests/` | pytest + `TestClient`; 1160 tests en verde al empezar (`uv run pytest -q`, 5 min 20 s) |

No hay ORM SQLAlchemy clásico con relaciones (`relationship`) en ningún modelo: el inventario usa SQLModel sin
relaciones declaradas y une SKU y movimientos con `JOIN` explícitos. TinyDB no tiene relaciones: usuario y perfil se
enlazan por `user_id`.

## 3. Tecnologías y versiones (comprobadas en el entorno, no en la documentación)

| Tecnología | Versión instalada |
| --- | --- |
| Python | 3.14.6 |
| FastAPI | 0.141.1 |
| Starlette | 1.7.0 |
| Pydantic | 2.13.5 (v2) |
| SQLModel / SQLAlchemy | 0.0.48 / 2.1.6 |
| TinyDB | 4.9.0 |
| Gestor | uv (`pyproject.toml` + `uv.lock`) |

Con FastAPI ≥ 0.89 la **anotación de retorno** de una función de ruta se usa como `response_model` si el decorador no
declara uno. Es lo que hacía toda la API: hay contrato, pero implícito.

## 4. Metodología

1. **Inventario desde la app registrada**, no desde los decoradores: un script recorre `app.routes` (en FastAPI 0.141
   los routers incluidos son objetos `_IncludedRouter`, cuyas rutas efectivas se leen con `effective_candidates()`) y
   lista método, ruta, router, función, `response_model` efectivo, código de estado y si el decorador lo declara.
2. Lectura de cada función de ruta, del esquema de respuesta, del servicio que lo construye y del modelo persistido.
3. Revisión de la OpenAPI generada (`app.openapi()`) para las rutas especiales.
4. **Consumidores reales**: búsqueda de las llamadas en `uis/backoffice/lib/*.ts`, sus tipos en `types/*.ts` y los
   campos que leen los componentes (`supplier.*`, `incident.*`, `movement.*`, `product.*`, `user.*`, `profile.*`).
   `uis/website` no llama a la API. Docker usa `/health` como healthcheck.
5. Revisión de campos sensibles en los modelos persistidos y de cómo se excluyen.
6. Revisión de consultas por endpoint (N+1, relaciones cargadas).

Clasificación (definición del enunciado):

- **✅ Serializado:** `response_model` **explícito** en el decorador y adecuado.
- **⚠️ Parcial:** hay esquema, pero implícito (anotación de retorno), incompleto, excesivo o inadecuado.
- **❌ Sin serializar:** devuelve `dict`, ORM u otra estructura sin esquema.
- **Especial:** respuesta sin cuerpo JSON (204 o descarga de fichero), no representable con un modelo Pydantic.

## 5. Inventario completo y estado original

33 endpoints de la aplicación + 4 rutas internas de FastAPI (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`,
`/redoc`, fuera de la auditoría). **Ningún decorador declaraba `response_model`.**

Consumidores: **BO** = `uis/backoffice` (fichero de `lib/`), **Swagger** = solo `/docs` o clientes HTTP (sin consumidor
en el frontend), **Docker** = healthcheck de Compose.

| # | Método | Ruta | Propósito | Router | Consumidor | `response_model` original | Respuesta real | Estado | Problema | Mejora |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/auth/login` | Login JSON | `auth.py` | BO `lib/auth.ts` | `Token` (implícito) | `Token` | ⚠️ | Contrato implícito | `response_model=Token` |
| 2 | POST | `/auth/token` | Login OAuth2 (Authorize) | `auth.py` | Swagger | `Token` (implícito) | `Token` | ⚠️ | Contrato implícito | `response_model=Token` |
| 3 | GET | `/auth/me` | Usuario actual + perfil | `auth.py` | BO `lib/auth.ts` (`AuthProvider`) | `UserWithProfile` (implícito) | `UserWithProfile` construido con `User.model_dump(exclude={"hashed_password"})` | ⚠️ | Contrato implícito; proyección por lista negra | `response_model` explícito; construir desde atributos (`from_attributes`) |
| 4 | POST | `/auth/forgot-password` | Pedir enlace de recuperación | `auth.py` | BO `lib/auth.ts` | `MessageResponse` (implícito) | Mensaje fijo | ⚠️ | Contrato implícito | `response_model=MessageResponse` |
| 5 | POST | `/auth/reset-password` | Fijar contraseña con el enlace | `auth.py` | BO `lib/auth.ts` | `MessageResponse` (implícito) | Mensaje fijo | ⚠️ | Contrato implícito | `response_model=MessageResponse` |
| 6 | POST | `/auth/change-password` | Cambiar contraseña con sesión | `auth.py` | BO `lib/auth.ts` | `Token` (implícito) | `Token` nuevo | ⚠️ | Contrato implícito | `response_model=Token` |
| 7 | POST | `/users` | Registro público | `users.py` | BO `lib/auth.ts` (ignora el cuerpo) | `UserWithProfile` (implícito) | Usuario **con `email`** + perfil | ⚠️ | **Devuelve el email** (el enunciado lo prohíbe en el registro); contrato implícito | Esquema propio de registro sin email |
| 8 | GET | `/users` | Listar usuarios (admin/manager) | `users.py` | Swagger | `list[UserPublic]` (implícito) | `UserPublic` por lista negra | ⚠️ | Contrato implícito; lista negra | `response_model` explícito; `from_attributes` |
| 9 | GET | `/users/{user_id}` | Ver un usuario | `users.py` | Swagger | `UserPublic` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 10 | PUT | `/users/{user_id}` | Email/rol/estado | `users.py` | Swagger | `UserPublic` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 11 | DELETE | `/users/{user_id}` | Baja | `users.py` | Swagger | — | 204 sin cuerpo | Especial | — | Documentar como «sin cuerpo» |
| 12 | GET | `/profiles/me` | Ver mi perfil | `profiles.py` | Swagger (BO lo recibe dentro de `/auth/me`) | `ProfilePublic` (implícito) | `ProfilePublic` vía `model_dump()` | ⚠️ | Contrato implícito | `response_model` explícito; `from_attributes` |
| 13 | PUT | `/profiles/me` | Editar mi perfil | `profiles.py` | BO `lib/auth.ts` | `ProfilePublic` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 14 | POST | `/suppliers` | Alta de proveedor | `suppliers.py` | BO `lib/suppliers.ts` | `Supplier` (implícito) | `Supplier` | ⚠️ | Implícito; **el esquema de salida hereda del de entrada** (`Supplier(SupplierCreate)`) | `Supplier` con campos y config propios |
| 15 | GET | `/suppliers` | Listar con filtros | `suppliers.py` | BO `lib/suppliers.ts` | `list[Supplier]` (implícito) | Ídem | ⚠️ | Ídem; un documento que no cumpla una regla de **entrada** (moneda/país) tumba el listado entero con un 500 | Ídem |
| 16 | GET | `/suppliers/{supplier_id}` | Ver proveedor | `suppliers.py` | Swagger | `Supplier` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 17 | PATCH | `/suppliers/{supplier_id}/rate` | Cambiar tarifa | `suppliers.py` | BO `lib/suppliers.ts` | `Supplier` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 18 | PATCH | `/suppliers/{supplier_id}/status` | Activar/suspender | `suppliers.py` | BO `lib/suppliers.ts` | `Supplier` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 19 | DELETE | `/suppliers/{supplier_id}` | Borrar proveedor | `suppliers.py` | Swagger (el BO no borra) | — | 204 sin cuerpo | Especial | — | Documentar |
| 20 | POST | `/api/incidents/analyze` | Analizar CSV de incidencias | `incidents.py` | BO `lib/incidencias.ts` | **`dict`** | `dict` de `analizar()` + `reglas` | ❌ | Sin esquema: OpenAPI anuncia «objeto cualquiera»; nada impide que un cambio del paquete añada datos personales (`customer_email`) a la respuesta; el tipo TS replica la forma a mano | Modelo `AnalysisResult` completo |
| 21 | GET | `/api/incidents/results/export` | Descargar `results.csv` | `incidents.py` | BO `lib/incidencias.ts` | — (`Response`) | CSV (`text/csv`) | Especial | OpenAPI dice `application/json` con esquema vacío | `response_class=Response` + `responses` con `text/csv` |
| 22 | POST | `/api/incidents` | Alta de incidencia | `incident_manager.py` | BO `lib/incidents.ts` | `Incident` (implícito) | `Incident` (sin `source_id`) | ⚠️ | Implícito; **`Incident` hereda de `IncidentCreate`** y repite sus validadores al responder | `Incident` con campos propios |
| 23 | GET | `/api/incidents` | Listar con filtros | `incident_manager.py` | BO `lib/incidents.ts` | `list[Incident]` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 24 | GET | `/api/incidents/summary` | Totales | `incident_manager.py` | BO `lib/incidents.ts` | `IncidentSummary` (implícito) | Ídem | ⚠️ | Contrato implícito | `response_model` explícito |
| 25 | GET | `/api/incidents/{incident_id}` | Ver incidencia | `incident_manager.py` | Swagger | `Incident` (implícito) | Ídem | ⚠️ | Como #22 | Como #22 |
| 26 | PATCH | `/api/incidents/{incident_id}/status` | Cambiar estado | `incident_manager.py` | BO `lib/incidents.ts` | `Incident` (implícito) | Ídem | ⚠️ | Como #22 | Como #22 |
| 27 | GET | `/inventory/products` | Listar SKUs con stock | `inventory.py` | BO `lib/inventory.ts` | `list[SKURead]` (implícito) | `SKURead` | ⚠️ | Contrato implícito | `response_model` explícito |
| 28 | POST | `/inventory/products` | Alta de SKU | `inventory.py` | Swagger / seed | `SKURead` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 29 | GET | `/inventory/products/{sku_id}` | SKU con stock | `inventory.py` | BO `lib/inventory.ts` | `SKURead` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 30 | POST | `/inventory/orders/inbound` | Entrada de stock | `inventory.py` | BO `lib/inventory.ts` | `StockEntryRead` (implícito) | `StockEntryRead.model_validate(ORM)` | ⚠️ | Ídem | Ídem |
| 31 | POST | `/inventory/orders/outbound` | Salida de stock | `inventory.py` | BO `lib/inventory.ts` | `StockExitRead` (implícito) | Ídem | ⚠️ | Ídem | Ídem |
| 32 | GET | `/inventory/orders` | Historial de movimientos | `inventory.py` | BO `lib/inventory.ts` | `list[Movement]` (implícito, unión discriminada) | Ídem | ⚠️ | Ídem | Ídem |
| 33 | GET | `/health` | Healthcheck | `main.py` | Docker, validación | **`dict[str, str]`** | `{"status": "ok"}` | ❌ | Diccionario sin esquema | `HealthResponse` |

**Recuento original:** ✅ 0 · ⚠️ 28 · ❌ 2 · especiales 3 (dos `DELETE` 204 y la descarga CSV).

Ninguno de los 28 ⚠️ filtraba datos sensibles: los esquemas inferidos ya eran listas blancas. Su defecto común es que
el contrato era **implícito** (depende de que nadie cambie la anotación de retorno a `dict` o a un modelo persistido).
`response_model_exclude`/`include` no se usa en ninguna ruta.

## 6. Problemas detectados

| ID | Problema | Endpoints | Severidad |
| --- | --- | --- | --- |
| P1 | El registro devuelve el `email` (requisito del enunciado: registro, login y recuperación no lo devuelven) | #7 | Alta |
| P2 | El analizador devuelve un `dict` sin contrato: OpenAPI no documenta la respuesta y un cambio del paquete podría exponer datos del CSV (correos de clientes) sin que nada lo impida | #20 | Alta |
| P3 | Ningún decorador declara `response_model`: el contrato depende de la anotación de retorno | 30 rutas JSON | Media |
| P4 | Esquemas de salida que heredan de los de entrada (`Supplier(SupplierCreate)`, `Incident(IncidentData(IncidentCreate))`): cualquier campo nuevo de entrada pasa a la salida, y los validadores de entrada (moneda/país, reglas del gestor, fechas) se vuelven a ejecutar al responder, de modo que un documento antiguo o editado a mano convierte el **listado entero** en un 500 | #14–18, #22–26 | Media |
| P5 | `/health` devuelve un diccionario sin esquema | #33 | Baja |
| P6 | Conversión a la salida por lista negra (`model_dump(exclude={"hashed_password"})`) en `/auth/me` y `/users`; los esquemas de salida no tienen `from_attributes` | #3, #7–10, #12–13 | Baja (el esquema de destino ya era una lista blanca) |
| P7 | La descarga CSV figura en OpenAPI como `application/json` con esquema vacío | #21 | Baja |
| P8 | Dos enums se llaman `Category` y OpenAPI los publica como `app__models__Category` y `app__inventory_schemas__Category` | #14–18, #27–32 | Baja (documentación) |

## 7. Campos sensibles o internos identificados

| Campo | Dónde vive | ¿Se exponía? | Cómo se protege (original) |
| --- | --- | --- | --- |
| `hashed_password` | `User` (TinyDB) | No | `UserPublic`/`UserWithProfile` no lo tienen + `exclude` explícito |
| `password_changed_at` | `User` | No | `UserPublic` no lo tiene (dato de control de sesiones) |
| `token_hash`, `expires_at`, `used_at` | `PasswordResetToken` | No | Ninguna ruta lo devuelve; el token en claro solo viaja en el email |
| Token de recuperación en claro | Email (`BackgroundTasks`) | No | `forgot-password` responde siempre el mismo `MessageResponse` |
| `invitation_code` | Entrada de `POST /users` | No | Nunca se guarda ni se devuelve |
| `source_id` (ID del CSV histórico) | `IncidentRecord` | No | `Incident` no lo tiene |
| `customer_email` del CSV | CSV del analizador | No (hoy) | `analizar()` no lo incluye — **sin contrato que lo garantice** (P2) |
| `SECRET_KEY`, `RESEND_API_KEY` | Entorno | No | Solo se leen en servidor; el 500 es genérico y el 422 no repite valores |
| `email` | `User` | Sí, en `POST /users`, `/auth/me` y `/users` | Ver P1; `/auth/me` puede devolverlo (enunciado) y `/users` es administración |

## 8. Consumidores y necesidades de payload

| Recurso | Campos que lee el backoffice | Campos devueltos | Conclusión |
| --- | --- | --- | --- |
| Proveedor (`/suppliers`) | `id`, `name`, `country`, `categories`, `rate_per_shipment`, `currency`, `status`, `service_zone`, `contact_email`, `notes`, `updated_at` | Los mismos 11 | El listado necesita el detalle completo (tabla con edición en línea). Sin esquema ligero aparte |
| Incidencia (`/api/incidents`) | `id`, `title`, `description`, `category`, `origin`, `branch`, `status`, `created_at` (+ `updated_at` en el tipo) | 9 campos | La tabla muestra la descripción. Sin cambio |
| SKU (`/inventory/products`) | `id`, `name`, `sku`, `client_name`, `category`, `warehouse`, `current_stock`, `stock_by_warehouse` | Los mismos | Sin cambio |
| Movimiento (`/inventory/orders`) | `id`, `movement_type`, `quantity`, `reference`/`exit_type`/`tracking_number`, `warehouse`, `created_at`, `user_uuid` («Tú»), `sku.name`, `sku.sku` | + `sku_id` y `sku` con 6 campos (`SKUSummary`) | `SKUSummary` ya es una proyección plana (sin stock ni movimientos). El briefing pide «movimientos con datos del SKU»: se mantiene |
| Usuario (`/auth/me`) | `id`, `email`, `role`, `created_at`, `profile.name/phone/address` | + `is_active`, `profile.id`, `profile.user_id` | `profile.user_id` repite `id`, pero es el contrato de AUTH-01 (relación 1:1 explícita) y no es sensible: se mantiene |
| Registro (`POST /users`) | Nada (el backoffice hace login a continuación) | Usuario con email + perfil | Quitar el email (P1) no rompe al consumidor |
| Analizador | Todas las claves de `ResultadoAnalisis` (`types/incidencias.ts`) | Las mismas | El modelo Pydantic debe reproducir exactamente esa forma |

**Paginación:** ningún listado la tiene y ningún consumidor la pide (decenas de registros); no se introduce.

**Consultas:** sin N+1. `/inventory/products` calcula el stock de todos los SKUs con dos consultas agregadas
(`GROUP BY sku_id, warehouse`) y `/inventory/orders` une SKU y movimiento con `JOIN` en dos consultas. Los recursos de
TinyDB se leen de un único fichero JSON por petición.

## 9. Autenticación

| Flujo | Endpoint | Respuesta original | ¿Contraseña/hash? | ¿Tokens internos? | ¿Email? | Veredicto |
| --- | --- | --- | --- | --- | --- | --- |
| Registro | `POST /users` | `UserWithProfile` (201) | No | No | **Sí** | ❌ incumple «sin email» (P1) |
| Login | `POST /auth/login`, `POST /auth/token` | `Token` (`access_token`, `token_type`, `expires_in`) | No | Solo el JWT de acceso, que es el fin del endpoint | No | ✅ contenido correcto (implícito) |
| Forgot password | `POST /auth/forgot-password` | `{"message": …}` fijo, 200 siempre | No | No (el token va por email) | No | ✅ no enumera: mismo cuerpo, envío en segundo plano, mismo 200 con usuario inactivo o inexistente |
| Reset password | `POST /auth/reset-password` | `{"message": …}` | No | No | No | ✅ un solo mensaje para cualquier enlace no válido |
| Cambio de contraseña | `POST /auth/change-password` | `Token` nuevo | No | Solo el JWT nuevo | No | ✅ |
| Usuario actual | `GET /auth/me` | `UserWithProfile` | No | No | Sí (permitido) | ✅ contenido; ⚠️ lista negra (P6) |

Refresh token: **no existe** en la API (JWT de acceso con caducidad; el backoffice vuelve a iniciar sesión).

## 10. Mejoras recomendadas

1. Declarar `response_model` en el decorador de las 30 rutas JSON (P3).
2. Esquema de respuesta de registro sin email (P1) y adaptar el tipo del backoffice.
3. `AnalysisResult` para el analizador (P2), con la forma exacta que consume el backoffice.
4. Esquemas de salida con campos propios y `ConfigDict(from_attributes=True)`, sin heredar de los de entrada (P4, P6).
5. `HealthResponse` (P5).
6. Documentar en OpenAPI la descarga CSV como `text/csv` y los 204 sin cuerpo (P7).
7. Nombres únicos para los enums de categoría en OpenAPI (P8), sin cambiar valores ni imports.
8. Tests de contrato y de seguridad que fallen si un endpoint pierde su `response_model` o expone un campo sensible.

## 11. Riesgos y prioridades

| Prioridad | Cambio | Riesgo de ruptura | Mitigación |
| --- | --- | --- | --- |
| 1 | P1 registro sin email | Bajo: el backoffice ignora la respuesta; tests del alta | Revisar `AuthProvider.register` y tests de registro |
| 2 | P2 `AnalysisResult` | Medio: un tipo mal declarado daría 500 en el análisis | Probar con el CSV real (`scripts/incidents-trackflow.csv`) y comparar el JSON antes/después |
| 3 | P4 separación entrada/salida | Bajo: mismos campos y tipos | Comparar OpenAPI y respuestas antes/después |
| 4 | P3/P5/P7/P8 | Muy bajo (documentación del contrato) | Test que recorre todas las rutas |

## 12. Diseño de los contratos (Fase 3)

### 12.1 Principios

- **Lista blanca en cada respuesta:** los esquemas de salida declaran sus campos uno a uno; nunca heredan de un esquema
  de entrada ni de un modelo persistido (`User`, `Profile`, `IncidentRecord`, tablas SQLModel).
- `ConfigDict(from_attributes=True)` en los esquemas de salida: se construyen directamente desde el objeto persistido
  (`UserPublic.model_validate(user)`, `StockEntryRead.model_validate(entry)`), sin `model_dump(exclude=…)`.
- `response_model` **explícito en el decorador** de toda ruta con cuerpo JSON. La anotación de retorno se mantiene
  (tipado del código), pero el contrato lo fija el decorador.
- Nombres de campo y tipos **sin cambios** salvo el email del registro: el backoffice y sus tipos TS no cambian.
- Sin paginación nueva, sin capas nuevas, sin dependencias nuevas.

### 12.2 Esquemas

| Esquema | Tipo | Estado | Campos | Uso |
| --- | --- | --- | --- | --- |
| `RegisterResponse` | Autenticación | **Nuevo** | `id`, `role`, `is_active`, `created_at`, `profile` (`ProfilePublic`) | `POST /users`. Sin `email` (P1) ni credenciales |
| `UserPublic` | Detalle/listado | Modificado: `from_attributes` | `id`, `email`, `role`, `is_active`, `created_at` | `GET/PUT /users…` (administración) |
| `UserWithProfile` | Autenticación | Reutilizado (hereda `from_attributes`) | `UserPublic` + `profile` | `GET /auth/me` (incluye email: permitido) |
| `ProfilePublic` | Detalle | Modificado: `from_attributes` | `id`, `user_id`, `name`, `phone`, `address` | `/profiles/me`, anidado en `/auth/me` y registro |
| `Token`, `MessageResponse` | Autenticación | Reutilizados | sin cambios | login, token, change-password / forgot, reset |
| `Supplier` | Detalle/listado | **Reescrito** sin heredar de `SupplierCreate` | `id`, `name`, `country`, `categories`, `rate_per_shipment`, `currency`, `status`, `service_zone`, `contact_email`, `notes`, `updated_at` | `/suppliers…` |
| `Incident` | Detalle/listado | **Reescrito** sin heredar de `IncidentData` | `id`, `title`, `description`, `category`, `origin`, `branch`, `status`, `created_at`, `updated_at` | `/api/incidents…` |
| `IncidentSummary` | Agregado | Reutilizado | sin cambios | `/api/incidents/summary` |
| `ResultadoAnalisis` (+ `Totales`, `RegistroInvalido`, `PorFecha`, `Cruces`, `Satisfaccion`, `SatisfaccionGlobal`, `Regla`) | Agregado | **Nuevo** (`app/analysis_schemas.py`) | La forma exacta de `types/incidencias.ts` | `POST /api/incidents/analyze` (P2). `extra="ignore"`: una clave nueva del paquete no llega al cliente sin pasar por el contrato |
| `SKURead`, `StockEntryRead`, `StockExitRead`, `InboundMovement`, `OutboundMovement`, `SKUSummary` | Detalle/listado | Reutilizados (ya eran listas blancas con `from_attributes`) | sin cambios | `/inventory…` |
| `HealthResponse` | Auxiliar | **Nuevo** | `status: "ok"` | `/health` (P5) |
| `SupplierCategory`, `ProductCategory` | Enums | Renombrados (alias `Category` en cada módulo) | mismos valores | Nombres únicos en OpenAPI (P8) |

**Esquemas de entrada** (sin cambios, ya separados y revisados): `UserCreate` y `UserUpdate` con `extra="forbid"`
(rechazan `role`, `is_active`, `id`, `password`); `ProfileUpdate` y `UserUpdate` distinguen campo omitido
(`exclude_unset`) de `null` (perfil: `null` vacía el dato; usuario: `null` → 422). `SupplierCreate`, `IncidentCreate` y
los de inventario **ignoran** `id`, `status`, `created_at`, `updated_at` y `user_uuid` si llegan en el cuerpo: es una
decisión documentada de cada práctica (`memory-bank/techContext.md`) y el efecto de seguridad es el mismo (el cliente no
puede fijarlos). Se mantiene y se cubre con tests.

### 12.3 Relaciones

| Relación | Decisión | Justificación |
| --- | --- | --- |
| Usuario → perfil (`/auth/me`, registro) | Objeto anidado (`ProfilePublic`) | El backoffice muestra nombre, teléfono y dirección; relación 1:1, sin ciclos |
| Perfil → usuario | Solo el ID (`user_id`) | Contrato de AUTH-01; no se anida el usuario (evita el ciclo usuario ↔ perfil) |
| Movimiento → SKU (`/inventory/orders`) | `sku_id` + proyección plana `SKUSummary` (sin stock ni movimientos) | El historial muestra nombre y código; el briefing pide «movimientos con datos del SKU» |
| Entrada/salida creada → SKU | Solo `sku_id` | El formulario ya tiene el SKU elegido |
| SKU → stock | Campos calculados (`current_stock`, `stock_by_warehouse`) con dos agregados | Sin N+1 |
| Incidencia, proveedor | Sin relaciones | — |

### 12.4 Payload esperado por endpoint (cambios)

| Endpoint | Antes | Después |
| --- | --- | --- |
| `POST /users` | `{id, email, role, is_active, created_at, profile}` | `{id, role, is_active, created_at, profile}` |
| `POST /api/incidents/analyze` | `dict` libre | `ResultadoAnalisis` (mismas claves que hoy) |
| `GET /health` | `dict[str, str]` | `{"status": "ok"}` validado |
| `GET /api/incidents/results/export` | OpenAPI: JSON vacío | OpenAPI: `text/csv` (binario) |
| Resto | — | Mismo JSON; solo cambia que el contrato es explícito |

### 12.5 Rutas especiales

- `DELETE /users/{id}` y `DELETE /suppliers/{id}`: **204 sin cuerpo**. No llevan `response_model` porque no hay cuerpo
  que serializar; OpenAPI ya los documenta sin contenido.
- `GET /api/incidents/results/export`: descarga **CSV** (`Response`, `text/csv; charset=utf-8`, `Content-Disposition`).
  Se declara con `response_class=Response` y `responses={200: {"content": {"text/csv": …}}}`.

### 12.6 Consumidor afectado

`uis/backoffice`: `authApi.register` pasa a tipar la respuesta como `RegisteredUser` (`CurrentUser` sin `email`). El
componente que lo usa (`AuthProvider.register`) no lee el cuerpo, así que no cambia el comportamiento.
