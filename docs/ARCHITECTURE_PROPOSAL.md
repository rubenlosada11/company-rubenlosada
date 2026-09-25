# Backend Architecture Proposal — TrackFlow

| | |
| --- | --- |
| Estado | Propuesta para revisión (no implementada) |
| Fecha | 2026-09-25 |
| Dirigida a | Andrés Kim (CTO) y equipo de TrackFlow Tech |
| Alcance | Backend centralizado con **Python + FastAPI** para el monorepo `company-rubenlosada` |
| Fuentes internas | [`CONTEXT.es.md`](../CONTEXT.es.md), [`CONTEXT-trackflow.es.md`](../CONTEXT-trackflow.es.md), [`memory-bank/`](../memory-bank/), [`packages/shared/`](../packages/shared/), [`uis/`](../uis/), [`README.es.md`](../README.es.md) |

> **Convención del documento.** Se distinguen tres tipos de afirmación:
>
> - **Hecho**: está en el `CONTEXT` o en el repositorio (se cita la fuente).
> - **Decisión**: lo que esta propuesta recomienda, con su justificación.
> - **Supuesto arquitectónico**: hipótesis razonable que el `CONTEXT` no confirma. Se marca siempre como tal y
>   debe validarse antes de implementarla.

---

## 1. Executive Summary

TrackFlow es un operador logístico (3PL) de almacén, última milla y logística inversa que opera en Estados Unidos y
España con dos almacenes, 8 transportistas y siete áreas de negocio. Hoy **no existe backend**: el repositorio
contiene frontends y una librería TypeScript, ninguno persiste datos de TrackFlow, y los sistemas reales de la empresa
(dos SGA distintos, un ERP de 2010 y scripts sin documentar) no se hablan entre sí.

**Arquitectura propuesta:** un **monolito modular organizado por dominios de negocio**, con **capas internas**
(router → servicio → repositorio) dentro de cada dominio y una **capa de integraciones** que aísla los sistemas
externos (transportistas, SGA, ERP). Se implementaría como **una única aplicación FastAPI** en
`services/api/`, versionada bajo `/api/v1`, con un `APIRouter` por recurso, configuración por variables de entorno
(`pydantic-settings`) y comunicación con los frontends exclusivamente por HTTP/JSON.

**Por qué esta y no otra:**

- El equipo técnico es de **7 personas** y hoy no tiene CI/CD, Docker ni telemetría. Un sistema distribuido
  (microservicios) multiplicaría exactamente los problemas que la empresa ya sufre: integraciones frágiles y fallos
  que se descubren por WhatsApp.
- Las necesidades del `CONTEXT` se reparten en **áreas con fronteras claras** (almacén, última milla, devoluciones,
  CX, comercial, dirección). Organizar el código por esas áreas hace visibles los límites y permite que el backend
  crezca hito a hito sin reescribirse.
- La misma API tendrá **muchos consumidores**: website, backoffice, portal público de seguimiento, agentes de IA,
  workflows n8n y pipelines de datos. Un único punto de entrada con un contrato OpenAPI es más barato de mantener
  que varios backends.
- Es la estructura que ya anticipa el propio repositorio: el `README.es.md` define `services/` como “un backend
  FastAPI centralizado… con routers/módulos por dominio” y desaconseja “dividir en muchos microservicios al inicio”.

**No se propone** crear microservicios, ni un backend por frontend, ni infraestructura nueva en esta fase.

---

## 2. Project Context

### 2.1 Qué es la empresa y qué problema resuelve (hechos)

| Pregunta | Respuesta | Fuente |
| --- | --- | --- |
| Tipo de empresa | Logística de última milla y gestión de almacenes para marcas de e-commerce (moda, electrónica, cosmética). Fundada en 2009, ~130 empleados, ~9 M€/año. | `CONTEXT.es.md`, `CONTEXT-trackflow.es.md` |
| Problema que resuelve a sus clientes | Las marcas saben fabricar y vender, no hacer llegar el producto. TrackFlow almacena, prepara, envía y gestiona devoluciones: toda la operación desde el pedido hasta la entrega o devolución. | `CONTEXT.es.md` |
| Mercados | Estados Unidos (almacén en Los Ángeles; UPS, FedEx, DHL) y España (almacén en Zaragoza; MRW, SEUR, DHL), más dos transportistas locales sin nombre. | `CONTEXT.es.md` |
| Problema interno (motivo de TrackFlow Tech) | Dos SGA distintos sin inventario compartido; pedidos que llegan por email y se transcriben a mano; asignación manual de transportista; sin datos de rendimiento de transportistas; devoluciones (18–25 % del volumen) revisadas una a una; ~80 % de consultas de CX automatizables; informe ejecutivo hecho a mano; sin telemetría; desplegar tarda 1–2 semanas. | `CONTEXT.es.md` |

### 2.2 Actores

| Actor | Tipo | Qué necesita del backend |
| --- | --- | --- |
| Marcas cliente (B2B) | Externo | Ver su operación: stock, envíos, devoluciones, informes. |
| Consumidor final (B2C) | Externo, anónimo | Saber dónde está su paquete y el estado de su devolución. |
| Prospectos (leads) | Externo | Enviar el formulario de solicitud de información (Hito 1). |
| Operarios y responsables de almacén (~70 + 2) | Interno | Consultar stock y pedidos de ambos almacenes. |
| Coordinadores de última milla (6) | Interno | Asignar transportista, seguir envíos, gestionar incidencias. |
| Equipo de logística inversa (5) | Interno | Aprobar/rechazar devoluciones, registrar inspección y resolución. |
| Agentes de CX (15) | Interno | Responder consultas con datos de envíos y devoluciones; tickets. |
| Account managers y desarrollo de negocio (8) | Interno | Perfil de cliente, contratos, renovaciones, leads. |
| Dirección (CEO: Thomas Harry) | Interno | KPIs por país, informe semanal, alertas. |
| Tecnología (7) | Interno | Salud del sistema, logs, integraciones documentadas. |
| Sistemas externos | Máquina | APIs de 8 transportistas, SGA de Los Ángeles (software comercial), SGA de Zaragoza (hoja de cálculo avanzada), ERP corporativo. |
| Agentes de IA, workflows y pipelines del monorepo | Máquina (interno) | `agents/`, `mcps/`, `workflows/`, `data/pipelines/` consumirán la misma API. |

### 2.3 Procesos principales (hechos)

1. **Entrada de pedido** → recepción (hoy por email) → picking y packing en uno de los dos almacenes.
2. **Envío** → selección de transportista → entrega → seguimiento → incidencias (pérdidas, fallidas, direcciones).
3. **Devolución** → aprobar/rechazar → recogida → inspección → reacondicionar o desechar.
4. **Atención al cliente** → consultas B2B y B2C por email, WhatsApp y teléfono.
5. **Comercial** → captación de leads → contrato anual → seguimiento de salud del cliente → renovación.
6. **Dirección** → consolidación semanal de KPIs por país.

### 2.4 Entidades de negocio que ya existen en el repositorio (hechos)

| Entidad | Dónde | Atributos relevantes |
| --- | --- | --- |
| `Carrier` | [`packages/shared/types/models.ts`](../packages/shared/types/models.ts) | `name`, `country` (`US`/`ES`), `costPerKgEur`, `onTimeDeliveryRate` |
| `Shipment` | idem | `trackingNumber`, `clientId`, `carrierId`, `originWarehouse` (`Los Angeles`/`Zaragoza`), `destinationCountry`, `weightKg`, `costEur`, `status` (`pending`/`in_transit`/`delivered`/`delayed`/`lost`), fechas |
| `ReturnRequest` | idem | `shipmentId`, `clientId`, `reason` (5 motivos), `status` (`pending_review`/`approved`/`rejected`/`refurbished`/`discarded`), fechas |
| `Client` | idem | `companyName`, `country`, `productType`, `monthlyShipmentVolume`, `contractStartDate`, `contractEndDate`, `accountManager` |
| Lead (solicitud de información) | [`CONTEXT-trackflow.es.md`](../CONTEXT-trackflow.es.md), [`uis/landing/formulario/`](../uis/landing/formulario/) | 12 campos con validaciones definidas; hoy el envío **se simula** en cliente (no se persiste). |
| Reglas de validación | [`packages/shared/utils/validations.ts`](../packages/shared/utils/validations.ts) | Peso > 0, coste ≥ 0, coherencia de fechas, estados permitidos, fin de contrato posterior al inicio… |
| Agregaciones | [`packages/shared/utils/transformations.ts`](../packages/shared/utils/transformations.ts) | Tasa de entrega a tiempo y coste medio por kg por transportista, devoluciones por motivo, clientes a renovar en 90 días. |

Entidades que el `CONTEXT` menciona pero **no están modeladas**: SKU/stock por almacén, pedido entrante, evento de
tracking, incidencia, regla de aprobación de devoluciones, inspección, ticket, contrato como entidad propia, KPI.

### 2.5 Estado técnico actual (hechos)

- **Sin backend.** `services/` solo contiene README. No hay base de datos, Docker, CI/CD ni tests
  ([`memory-bank/techContext.md`](../memory-bank/techContext.md)).
- **Frontends Next.js 16 + TypeScript** independientes entre sí: `uis/website` (público, `:3001`) y
  `uis/backoffice` (interno, `:3002`, **publicado sin autenticación**), con datos estáticos tipados en `lib/`.
- **Precedente de consumo de API:** `uis/talent-pipeline-tracker` ya consume una API externa (con formato de error
  FastAPI `{"detail": [...]}`) a través de un único módulo [`lib/http.ts`](../uis/talent-pipeline-tracker/lib/http.ts)
  y la variable `NEXT_PUBLIC_API_URL`, que falla al arrancar si no está definida.
- **Despliegue actual:** subdominios de `rubenlosada.com` detrás de Cloudflare; cada app se extrae del repositorio y
  se construye en el servidor (`npm ci` + `npm run build`).
- Monorepo **sin workspace raíz**: cada proyecto es autónomo, con sus dependencias y su lockfile.

### 2.6 Necesidades futuras que condicionan la arquitectura

- Los siguientes hitos del curso (`README.es.md`): **Backend, Telemetría, RAG, Agentes, Workflows, Tiempo real**.
  Todos se apoyarán en esta API.
- El `CONTEXT` pide varias piezas **“en tiempo real”** (stock, dashboards, KPIs) y **disponibilidad 24/7** para el
  portal de seguimiento y el agente de CX.
- Integración con **8 APIs de transportistas** y **2 SGA** heterogéneos.
- Dos países → dos zonas horarias y, previsiblemente, dos monedas.

> **Supuesto arquitectónico — volumen.** El `CONTEXT` habla de “cientos de pedidos” diarios por almacén y 8
> transportistas. Se asume un orden de magnitud de miles (no millones) de operaciones de escritura al día. Esto
> cabe holgadamente en una sola aplicación FastAPI con una base de datos relacional.

---

## 3. Business and System Requirements

### 3.1 Requisitos funcionales (derivados de “Qué necesitan” de cada área)

| Área (`CONTEXT`) | Capacidad de backend | Prioridad propuesta |
| --- | --- | --- |
| Comercial | Persistir leads del formulario; clientes y contratos; alertas de renovación a 90 y 30 días. | Fase 1 |
| Última milla | Transportistas; envíos; **endpoint unificado de tracking**; métricas de rendimiento; motor de selección de transportista. | Fase 1–2 |
| Logística inversa | Solicitudes de devolución; **aprobación automática con reglas por cliente**; resolución; análisis por motivo. | Fase 1–2 |
| Operaciones de almacén | **API de inventario unificada** (stock por SKU y almacén); pedidos entrantes; alertas de stock bajo. | Fase 2–3 (depende de integrar los dos SGA) |
| Experiencia del cliente | Tickets unificados; datos para el agente de CX (seguimiento y devoluciones). | Fase 3 |
| Dirección | KPIs por país (volumen, entrega a tiempo, coste, devoluciones, satisfacción); informe semanal. | Fase 3 |
| Tecnología | Health checks, logging estructurado, base para telemetría. | Fase 1 (transversal) |

Las fases se detallan en la [sección 15](#15-future-evolution). Tres necesidades ya tienen **lógica escrita en
TypeScript** en `packages/shared` (rendimiento de transportistas, devoluciones por motivo, renovaciones), lo que las
convierte en candidatas naturales a los primeros endpoints.

### 3.2 Requisitos no funcionales

| Requisito | Por qué en TrackFlow | Implicación arquitectónica |
| --- | --- | --- |
| **Aislamiento de datos entre marcas** | Una marca nunca debe ver envíos, stock o devoluciones de otra; las renovaciones dependen de la confianza. | Filtro por cliente obligatorio en la capa de datos, no opcional en el endpoint (ver riesgo R1). |
| **Tolerancia a fallos de terceros** | 8 transportistas y 2 SGA con disponibilidad y formatos distintos. | Capa de integraciones con timeouts y normalización; un fallo de UPS no puede tumbar `/shipments`. |
| **Disponibilidad del tracking público** | El consumidor final consulta fuera del horario de oficina (`CONTEXT`: sistemas 24/7). | Endpoint público separado, ligero y cacheable. |
| **Observabilidad** | Hoy los fallos se descubren por WhatsApp. | Health check, logs estructurados con ID de petición desde el primer día. |
| **Evolución por hitos** | Cada hito del curso añade capacidades (RAG, agentes, tiempo real). | Añadir un dominio no debe obligar a tocar los demás. |
| **Equipo pequeño** | 7 personas en tecnología. | Un solo despliegue, un solo lenguaje de backend, convenciones de FastAPI estándar. |
| **Bilingüe** | Operación en EE. UU. y España; el idioma base del proyecto es el español. | La API devuelve códigos y enums estables; los textos visibles los traduce el frontend. |

---

## 4. Architectural Alternatives Considered

| Alternativa | Qué resuelve | Ventajas para TrackFlow | Inconvenientes para TrackFlow | Veredicto |
| --- | --- | --- | --- | --- |
| **MVC clásico** | Separar datos, presentación y control en apps que renderizan HTML. | Patrón conocido. | La “V” ya vive en Next.js: el backend solo expone JSON. Sin una capa de servicio explícita, la lógica acaba en los controladores (aprobación de devoluciones, selección de transportista dentro del endpoint). No dice nada de cómo separar dominios. | Descartada |
| **Capas por tipo (layer-first)**: `routers/`, `services/`, `repositories/`, `models/`, `schemas/` en la raíz | Separar responsabilidades técnicas. | Muy sencilla; es la forma de la [plantilla full-stack de FastAPI](https://github.com/fastapi/full-stack-fastapi-template) (`api/routes`, `crud.py`, `models.py`). Ideal para 1–2 recursos. | Con 6 dominios, cada carpeta mezcla todos: cambiar “devoluciones” obliga a tocar 5 carpetas, y nada impide que `returns` importe tablas de `shipments`. Los límites de negocio no se ven en el código. | Se adopta **dentro** de cada dominio, no como organización principal |
| **Modular por dominios** | Agrupar el código por área de negocio. | Refleja las áreas del `CONTEXT`; cada hito añade un módulo; facilita asignar responsables. | Más carpetas; exige reglas explícitas sobre cómo se comunican los dominios. | Se adopta |
| **Monolito modular** | Un solo despliegue con módulos de límites claros. | Un proceso, una base de datos, transacciones locales, un pipeline de despliegue. Los módulos pueden extraerse más tarde si hay una razón real. | Un fallo grave afecta a toda la API; no se escala un dominio por separado. | Se adopta (junto con la anterior) |
| **Microservicios** | Equipos y despliegues independientes a gran escala. | Escalado y despliegue por servicio. | Coste de red, observabilidad distribuida, contratos entre servicios, varias bases de datos… para un equipo de 7 sin CI/CD ni telemetría. Fowler: incluso arquitectos expertos “tienen grandes dificultades para acertar los límites al principio”, y refactorizar entre servicios es mucho más caro que dentro de un monolito. | Descartada ahora (ver criterios de extracción en §15) |
| **Serverless (FaaS)** | Cargas esporádicas sin servidor permanente. | Encaja con tareas puntuales: informe del lunes, webhooks de transportistas. | La API tiene que estar siempre disponible (tracking 24/7), mantiene conexiones a BD y agrega varias fuentes por petición; los arranques en frío y los límites de conexiones juegan en contra. El despliegue actual es un servidor propio detrás de Cloudflare: introduciría un proveedor y un modelo operativo nuevos. Para tareas programadas el repo ya prevé `workflows/` (n8n). | Descartada como arquitectura principal |

**Qué significa aquí “escalar”** (para no usar el término en vacío):

1. **Escalar en funcionalidad:** pasar de 0 a ~30 iniciativas del `CONTEXT` (el backoffice lista 33) sin que el
   código se convierta en un único fichero de endpoints. → Lo resuelve la modularidad por dominios.
2. **Escalar en integraciones:** añadir un noveno transportista o sustituir el SGA-hoja de cálculo de Zaragoza sin
   tocar los dominios. → Lo resuelve la capa de integraciones.
3. **Escalar en consumidores:** website, backoffice, portal público, agentes, n8n y pipelines usando el mismo
   contrato. → Lo resuelven el versionado y OpenAPI.
4. **Escalar en carga:** con el volumen supuesto basta con ejecutar varios *workers* del mismo proceso detrás del
   proxy. No hace falta repartir el sistema en servicios.

---

## 5. Proposed Architecture

### 5.1 Decisión

> **Decisión:** monolito modular por dominios de negocio + arquitectura en capas dentro de cada dominio + capa de
> integraciones para sistemas externos, implementado como **una aplicación FastAPI** en `services/api/`.

**Por qué `services/api/` y no `backend/`:** el repositorio ya define `services/` como la carpeta de la “API
FastAPI centralizada” (`README.es.md`) y pide una subcarpeta por servicio. Crear `backend/` en la raíz rompería
la estructura de primer nivel (un cambio que [`AGENTS.md`](../AGENTS.md) marca como arquitectónico).

### 5.2 Vista de contexto

```text
                ┌───────────────────────── Consumidores ─────────────────────────┐
                │ uis/website   uis/backoffice   portal de tracking (futuro)     │
                │ agents/ + mcps/   workflows/ (n8n)   data/pipelines/           │
                └───────────────────────────────┬────────────────────────────────┘
                                                │ HTTPS · JSON · /api/v1
                                                ▼
┌──────────────────────────────── services/api (FastAPI) ─────────────────────────────────┐
│  api/        routers por recurso · dependencias (sesión, usuario, ámbito de cliente)   │
│  domains/    commercial · last_mile · reverse_logistics · warehouse ·                  │
│              customer_service · reporting · identity                                   │
│  integrations/  carriers (UPS, FedEx, DHL, MRW, SEUR, 2 locales) · wms (LA, ZGZ) · erp │
│  core/       configuración · errores · seguridad · logging                             │
└───────────────┬───────────────────────────────────────────────┬─────────────────────────┘
                ▼                                               ▼
      Base de datos relacional                     APIs y sistemas externos
      (Supuesto: PostgreSQL)                       (transportistas, 2 SGA, ERP)
```

### 5.3 Capas dentro de cada dominio

| Capa | Responsabilidad | Conoce FastAPI | Conoce la BD |
| --- | --- | --- | --- |
| **Router** (`api/v1/routers/`) | Traducir HTTP ↔ dominio: ruta, parámetros, esquema de entrada/salida, código de estado, dependencias (auth, sesión). | Sí | No (recibe la sesión y la pasa) |
| **Servicio** (`domains/<d>/service.py`) | Reglas de negocio y orquestación: aprobar una devolución, elegir transportista, calcular renovaciones. Lanza excepciones de dominio. | **No** | No directamente |
| **Repositorio** (`domains/<d>/repository.py`) | Consultas y persistencia de las tablas **de su dominio**. Siempre filtra por cliente cuando aplica. | No | Sí |
| **Integración** (`integrations/`) | Hablar con un sistema externo y devolver datos **normalizados** al vocabulario de TrackFlow. | No | No |

Dirección de las dependencias: `api → domains → (repositories, integrations) → db/externos`. `core` puede usarse
desde cualquier capa. Nunca al revés: un servicio no importa un router ni `fastapi`.

**Por qué el servicio no conoce FastAPI:** la misma lógica la reutilizarán procesos que no son HTTP (el pipeline
de ingesta de pedidos, un *worker* futuro, tests unitarios). Si `ReturnService` lanzase `HTTPException`, no se
podría usar fuera de una petición.

### 5.4 Reglas entre dominios

1. Un dominio solo accede a **sus** tablas. Si `reverse_logistics` necesita un envío, llama a
   `last_mile.service.get_shipment(...)`; no importa el modelo ni el repositorio de `last_mile`.
2. `reporting` no tiene tablas propias al principio: compone datos llamando a los servicios de los demás
   dominios. Si una consulta es demasiado costosa, se crea una vista o tabla de lectura específica (ver §15).
3. `integrations/` no contiene reglas de negocio: `UPS dice "D"` → `ShipmentStatus.delivered`, nada más.

---

## 6. Architectural Principles

1. **Proporcionalidad.** Cada capa o carpeta debe responder a un problema del `CONTEXT`. Si no, no se crea.
2. **Límites por negocio, capas por técnica.** Primero se decide *qué área* es dueña de algo; después *en qué capa*
   va.
3. **Una sola fuente de verdad de las reglas.** Las reglas de negocio viven en los servicios del backend. La
   validación del frontend es de experiencia de usuario, no de seguridad.
4. **Contrato explícito.** La API se describe en OpenAPI (FastAPI lo genera) y se versiona.
5. **Configuración fuera del código.** Nada que cambie entre entornos (URLs, credenciales, orígenes) está escrito
   en el código ([Twelve-Factor, Config](https://12factor.net/config)).
6. **Los sistemas externos no dictan el modelo.** Los formatos de UPS, SEUR o del SGA de Zaragoza se traducen en la
   frontera.
7. **Fallar pronto y con claridad.** Configuración obligatoria ausente → la API no arranca; error de dominio →
   respuesta HTTP coherente y documentada.

---

## 7. Backend Structure

### 7.1 Árbol propuesto

```text
services/
└── api/
    ├── README.md                     # cómo ejecutar, variables, convenciones del servicio
    ├── pyproject.toml                # dependencias y [tool.fastapi] entrypoint = "app.main:app"
    ├── .env.example                  # variables documentadas, sin valores secretos (el .env real no se versiona)
    ├── alembic.ini
    ├── alembic/
    │   └── versions/                 # migraciones de esquema
    ├── app/
    │   ├── __init__.py
    │   ├── main.py                   # crea FastAPI, CORS, handlers de error, include_router(api_v1)
    │   ├── core/
    │   │   ├── config.py             # Settings (pydantic-settings) + get_settings() con lru_cache
    │   │   ├── errors.py             # excepciones de dominio base + exception handlers
    │   │   ├── security.py           # tokens / hashing (cuando se implemente auth)
    │   │   └── logging.py            # logs estructurados, ID de petición
    │   ├── db/
    │   │   ├── base.py               # base declarativa de SQLAlchemy
    │   │   └── session.py            # engine + get_session() con yield (una sesión por petición)
    │   ├── api/
    │   │   ├── deps.py               # SessionDep, SettingsDep, CurrentUser, ClientScope, Pagination
    │   │   └── v1/
    │   │       ├── router.py         # api_router = APIRouter(prefix="/api/v1") + include_router de cada recurso
    │   │       └── routers/
    │   │           ├── auth.py
    │   │           ├── leads.py
    │   │           ├── clients.py
    │   │           ├── carriers.py
    │   │           ├── shipments.py
    │   │           ├── public_tracking.py
    │   │           ├── returns.py
    │   │           ├── inventory.py
    │   │           ├── orders.py
    │   │           ├── tickets.py
    │   │           └── reports.py
    │   ├── domains/
    │   │   ├── commercial/           # clientes, contratos, leads
    │   │   │   ├── models.py
    │   │   │   ├── schemas.py
    │   │   │   ├── repository.py
    │   │   │   ├── service.py
    │   │   │   └── exceptions.py
    │   │   ├── last_mile/            # transportistas, envíos, tracking, incidencias
    │   │   │   ├── models.py · schemas.py · repository.py · service.py · exceptions.py
    │   │   │   └── carrier_selection.py   # motor de recomendación (lógica pura)
    │   │   ├── reverse_logistics/    # devoluciones, reglas de aprobación, inspección
    │   │   │   ├── models.py · schemas.py · repository.py · service.py · exceptions.py
    │   │   │   └── approval_rules.py      # evaluación de reglas por cliente (lógica pura)
    │   │   ├── warehouse/            # almacenes, stock por SKU, pedidos entrantes
    │   │   ├── customer_service/     # tickets (fase 3)
    │   │   ├── reporting/            # KPIs: service.py + schemas.py, sin tablas propias
    │   │   └── identity/             # usuarios internos y de marca, roles
    │   └── integrations/
    │       ├── carriers/
    │       │   ├── base.py           # contrato común (p. ej. get_tracking, create_label)
    │       │   ├── ups.py · fedex.py · dhl.py · mrw.py · seur.py
    │       │   └── registry.py       # qué adaptador corresponde a cada transportista/país
    │       ├── wms/
    │       │   ├── base.py
    │       │   ├── los_angeles.py    # SGA comercial
    │       │   └── zaragoza.py       # hoja de cálculo avanzada
    │       └── erp/                  # cuando se aborde
    └── tests/
        ├── conftest.py               # TestClient, BD de test, dependency_overrides
        ├── api/                      # tests HTTP por router
        └── domains/                  # tests unitarios de servicios y reglas
```

No todo se crea el primer día: la estructura muestra el destino. Los dominios `warehouse`, `customer_service` y
`reporting` y las carpetas de integraciones se añaden cuando llega su fase (§15). Los dos transportistas locales no
tienen nombre en el `CONTEXT`, por eso no aparecen como fichero.

### 7.2 Responsabilidad de cada directorio

| Directorio | Contiene | No debe contener | Relación |
| --- | --- | --- | --- |
| `app/main.py` | Creación de `FastAPI(...)`, metadatos OpenAPI (`openapi_tags`), middleware CORS, registro de handlers de error, `include_router` del router v1, health check. | Endpoints de negocio, consultas, lógica. | Punto de ensamblaje: importa `api/v1/router.py` y `core/`. |
| `core/` | Configuración, errores base, seguridad, logging. Código transversal sin conocimiento de ningún dominio. | Nada específico de envíos, devoluciones, etc. | Lo usan todas las capas. |
| `db/` | Motor, sesión por petición, base declarativa. | Consultas de negocio (van en los repositorios). | Los repositorios reciben la sesión creada aquí. |
| `api/deps.py` | Dependencias reutilizables como alias `Annotated` (`SessionDep`, `CurrentUser`, `ClientScope`, `Pagination`). | Reglas de negocio. | Las usan los routers. |
| `api/v1/routers/` | Un fichero por recurso con su `APIRouter`: rutas, `response_model`, códigos de estado, dependencias. | SQL, llamadas a transportistas, reglas de aprobación, `if` de negocio. | Llaman a `domains/<d>/service.py`. |
| `domains/<d>/models.py` | Tablas SQLAlchemy del dominio. | Esquemas de la API; lógica. | Solo los importa el repositorio de su dominio (y Alembic). |
| `domains/<d>/schemas.py` | Modelos Pydantic de entrada/salida (`ShipmentCreate`, `ShipmentPublic`, `TrackingPublic`…). | Acceso a BD. | Contrato de la API; lo usan routers y servicios. |
| `domains/<d>/repository.py` | Consultas y escrituras de las tablas del dominio. | Reglas de negocio, HTTP. | Lo usa solo el servicio de su dominio. |
| `domains/<d>/service.py` | Casos de uso y reglas. Única puerta de entrada al dominio desde fuera. | `fastapi`, `HTTPException`, SQL literal. | Llama a su repositorio, a `integrations/` y a servicios de otros dominios. |
| `domains/<d>/exceptions.py` | Errores de negocio (`ShipmentNotFound`, `ReturnWindowExpired`…). | Códigos HTTP. | `core/errors.py` los traduce a HTTP. |
| `integrations/` | Clientes HTTP/ficheros hacia sistemas externos y traducción a tipos de TrackFlow. | Decisiones de negocio, acceso a nuestras tablas. | La usan los servicios, a través del contrato de `base.py`. |
| `tests/` | Tests de API (`TestClient`) y de servicios. | Datos reales o credenciales. | Sustituyen dependencias con `app.dependency_overrides`. |
| `alembic/` | Historial de migraciones del esquema. | Datos de negocio. | Generado a partir de `domains/*/models.py`. |

---

## 8. Domain Organization

Los nombres de módulo están en inglés y *snake_case* para seguir la convención ya usada en el código del repo
(`packages/shared` y los identificadores de área del backoffice: `warehouse`, `last-mile`, `reverse-logistics`,
`customer-experience`, `commercial`, `executive`). La documentación y los textos siguen en español.

### 8.1 `commercial` — Comercial y relación con clientes

- **Representa:** la cartera de marcas cliente, sus contratos anuales y la captación de nuevas marcas.
- **Entidades:** `Client` (existe en `packages/shared`), `Lead` (campos definidos en el Hito 1).
  *Supuesto arquitectónico:* `Contract` como entidad separada del cliente (hoy son dos fechas dentro de `Client`),
  para poder guardar renovaciones sucesivas.
- **Operaciones:** registrar un lead; alta y consulta de clientes; listar contratos que vencen en N días.
- **Endpoints de ejemplo:**

  ```text
  POST   /api/v1/leads                      # formulario de solicitud de información (público)
  GET    /api/v1/leads                      # equipo comercial
  GET    /api/v1/clients
  GET    /api/v1/clients/{client_id}
  POST   /api/v1/clients
  GET    /api/v1/clients/renewals?within_days=90
  ```

- **Lógica de negocio:** las validaciones del formulario (empresa ≥ 2 caracteres, teléfono con prefijo, al menos un
  servicio…); el aviso de volumen “0-100 envíos/mes”; fin de contrato posterior al inicio; ventanas de alerta a 90 y
  30 días.

### 8.2 `last_mile` — Última milla y gestión de transportistas

- **Representa:** qué transportista lleva cada envío y en qué estado está.
- **Entidades:** `Carrier`, `Shipment` (existen). *Supuesto arquitectónico:* `TrackingEvent` (historial de estados
  normalizado) e `Incident` (pérdida, entrega fallida, dirección incorrecta).
- **Operaciones:** registrar envío; consultar tracking unificado; recomendar transportista por destino, peso y
  urgencia; métricas por transportista (entrega a tiempo, coste por kg).
- **Endpoints de ejemplo:**

  ```text
  GET    /api/v1/carriers
  GET    /api/v1/carriers/performance?country=ES
  GET    /api/v1/shipments?status=delayed&carrier_id=...&origin_warehouse=Zaragoza
  POST   /api/v1/shipments
  GET    /api/v1/shipments/{shipment_id}
  GET    /api/v1/shipments/{shipment_id}/tracking
  POST   /api/v1/shipments/carrier-recommendation
  GET    /api/v1/public/tracking/{tracking_number}   # consumidor final, sin login, datos mínimos
  ```

- **Lógica de negocio:** normalizar estados a `pending/in_transit/delivered/delayed/lost`; reglas de coherencia
  (peso > 0, entrega no anterior a creación); algoritmo de recomendación (reutiliza las métricas que hoy calcula
  `packages/shared`).

### 8.3 `reverse_logistics` — Logística inversa

- **Representa:** el ciclo de vida de un producto que vuelve.
- **Entidades:** `ReturnRequest` (existe). *Supuesto arquitectónico:* `ApprovalRule` (reglas por cliente, que el
  `CONTEXT` pide “configurables”) e `Inspection` (resultado de la inspección, manual o asistida por IA).
- **Operaciones:** crear devolución vinculada a un envío; evaluación automática de reglas; resolver
  (reacondicionar/desechar); estadísticas por motivo.
- **Endpoints de ejemplo:**

  ```text
  POST   /api/v1/returns
  GET    /api/v1/returns?status=pending_review&client_id=...
  GET    /api/v1/returns/{return_id}
  POST   /api/v1/returns/{return_id}/decision        # aprobar / rechazar (manual)
  POST   /api/v1/returns/{return_id}/inspection
  GET    /api/v1/returns/stats/by-reason
  GET    /api/v1/returns/rules/{client_id}            # reglas de aprobación de una marca
  PUT    /api/v1/returns/rules/{client_id}
  ```

  Las rutas fijas (`/stats/...`, `/rules/...`) se declaran antes que `/{return_id}`, porque FastAPI evalúa las
  rutas en orden.

- **Lógica de negocio:** reglas de aprobación por cliente; transiciones de estado válidas
  (`pending_review → approved → refurbished/discarded`); coherencia de fechas. La clasificación por imagen la hará
  un agente de `agents/`; el backend solo recibe y guarda su resultado.

### 8.4 `warehouse` — Operaciones de almacén

- **Representa:** stock y pedidos de los dos almacenes con una visión única.
- **Entidades:** `Warehouse` (Los Ángeles, Zaragoza: existen como valores). *Supuesto arquitectónico:* `Sku`
  (perteneciente a un cliente), `StockLevel` (SKU × almacén), `InboundOrder` (pedido entrante).
- **Operaciones:** stock de un SKU en ambos almacenes; registrar pedidos que llegan del pipeline de ingesta de
  emails; umbrales y alertas de stock bajo.
- **Endpoints de ejemplo:**

  ```text
  GET    /api/v1/inventory/{sku}                     # stock en los dos almacenes
  GET    /api/v1/inventory?warehouse=Los%20Angeles&below_threshold=true
  POST   /api/v1/orders                              # lo invoca data/pipelines (ingesta de emails)
  GET    /api/v1/orders/{order_id}
  ```

- **Lógica de negocio:** unificar dos fuentes con formatos distintos; decidir qué es “stock bajo” por SKU/cliente.
- **Nota:** depende de los adaptadores `integrations/wms/`. Es la necesidad de mayor valor para Operaciones, pero
  también la de mayor incertidumbre técnica (una de las fuentes es una hoja de cálculo), por eso va en fase 2–3.

### 8.5 `customer_service` — Experiencia del cliente (fase 3)

- **Entidades:** *Supuesto arquitectónico:* `Ticket` con canal (email, WhatsApp, teléfono), tipo de solicitante
  (marca o consumidor) y estado.
- **Endpoints de ejemplo:** `GET/POST /api/v1/tickets`, `PATCH /api/v1/tickets/{ticket_id}`.
- **Qué no contiene:** el agente de CX ni la base de conocimiento RAG. Esos viven en `agents/` y `data/`, y
  consumen `last_mile` y `reverse_logistics` **a través de la API**, igual que un humano desde el backoffice. Así
  el agente no duplica reglas de negocio.

### 8.6 `reporting` — Dirección ejecutiva

- **Representa:** KPIs agregados por país y periodo.
- **Entidades propias:** ninguna al principio.
- **Endpoints de ejemplo:** `GET /api/v1/reports/kpis?country=US&from=...&to=...`,
  `GET /api/v1/reports/weekly?week=...` (lo invocaría un workflow n8n el lunes a las 7:00).
- **Lógica:** volumen de envíos, tasa de entrega a tiempo, coste operativo, tasa de devoluciones. La satisfacción
  del cliente depende de datos que hoy no existen.

### 8.7 `identity` — Transversal

- **Entidades:** `User` con tipo (`internal` o `client`) y, para usuarios de marca, su `client_id`.
  *Supuesto arquitectónico:* roles por área (almacén, última milla, devoluciones, CX, comercial, dirección, tech).
- **Endpoints de ejemplo:** `POST /api/v1/auth/token`, `GET /api/v1/auth/me`.

### 8.8 Fuera del backend de TrackFlow

- **Talent Pipeline Tracker (Hito 3):** consume una API externa de 4Geeks; no forma parte de este dominio.
- **Tecnología** no es un dominio de negocio aquí: sus necesidades (health checks, logs, telemetría) se resuelven
  en `core/` y en el hito de Telemetría.

---

## 9. FastAPI Routers and Endpoints

### 9.1 Criterio de agrupación

- **Un `APIRouter` por recurso**, agrupado bajo su dominio (`leads.py` y `clients.py` → `commercial`). No existe
  un fichero con todos los endpoints.
- **Se separa también por audiencia** cuando cambian las reglas de seguridad: `public_tracking.py` expone el mismo
  dominio que `shipments.py`, pero sin login, con un esquema de respuesta mínimo (sin coste, cliente ni peso) y
  con límite de peticiones. Mezclarlos en un mismo router obligaría a excepciones de seguridad por endpoint.
- Umbral orientativo: si un router supera ~10–15 operaciones o mezcla dos recursos, se divide.

### 9.2 Cómo se configura cada router (sin código funcional)

| Elemento | Propuesta | Ejemplo en TrackFlow |
| --- | --- | --- |
| `prefix` | En el propio `APIRouter`, sin barra final (requisito de FastAPI). | `APIRouter(prefix="/shipments", ...)` |
| `tags` | Una etiqueta por recurso; descripciones en `openapi_tags` de `main.py` (el orden define el de `/docs`). | `tags=["Envíos"]`, `tags=["Devoluciones"]` |
| `dependencies` | Las comunes a todo el router van en el router, no repetidas en cada ruta. | `returns` exige `require_area("reverse_logistics")`; `public_tracking` solo el limitador. |
| `responses` | Respuestas de error compartidas documentadas una vez. | `{404: {"description": "Envío no encontrado"}}` |
| `response_model` | Siempre un esquema público explícito, nunca el modelo de tabla. | `ShipmentPublic`, `TrackingPublic` |

### 9.3 Versionado y relación con `main.py`

```text
main.py
  └── include_router(api_v1_router)            # prefix="/api/v1"
        ├── include_router(auth.router)        # /api/v1/auth
        ├── include_router(leads.router)       # /api/v1/leads
        ├── include_router(clients.router)     # /api/v1/clients
        ├── include_router(carriers.router)    # /api/v1/carriers
        ├── include_router(shipments.router)   # /api/v1/shipments
        ├── include_router(public_tracking.router)  # /api/v1/public/tracking
        ├── include_router(returns.router)     # /api/v1/returns
        ├── include_router(inventory.router)   # /api/v1/inventory   (fase 2-3)
        ├── include_router(orders.router)      # /api/v1/orders      (fase 2-3)
        ├── include_router(tickets.router)     # /api/v1/tickets     (fase 3)
        └── include_router(reports.router)     # /api/v1/reports     (fase 3)
GET /health                                     # fuera de la versión: lo consultan proxy y monitorización
```

- `main.py` **solo ensambla**: no define endpoints de negocio. Añadir un dominio = crear su router y una línea
  `include_router` en `api/v1/router.py`.
- **Versión en la ruta** (`/api/v1`): visible en logs y en el proxy, y fácil de configurar en los frontends. Los
  cambios compatibles (campos nuevos opcionales, endpoints nuevos) se quedan en `v1`. Un cambio incompatible crea
  `api/v2/` reutilizando los mismos servicios de dominio; `v1` convive hasta que website, backoffice y agentes
  migren.
- **Convenciones REST:** recursos en plural, IDs en la ruta, filtros como *query params* (los mismos criterios que ya
  usa `filterShipments` en `packages/shared`: estado, transportista, país, almacén, fechas), acciones que no son
  CRUD como sub-recursos (`/returns/{id}/decision`), `201` en creación, `204` sin cuerpo, `404`/`409`/`422` para
  errores.

---

## 10. Request Flow

Ejemplo real: un agente de CX (humano en el backoffice o el agente de IA) consulta dónde está un envío.

```text
Backoffice (Next.js)  ──  GET {API_BASE_URL}/api/v1/shipments/{id}/tracking  +  Authorization
        │
        ▼
CORSMiddleware + middleware de logging (ID de petición)
        │
        ▼
Router shipments.py
  · valida {id} y la query
  · dependencias: CurrentUser → ClientScope (si es usuario de marca, solo sus envíos), SessionDep
        │
        ▼
last_mile.service.get_tracking(id, scope)
  · pide el envío al repositorio (filtrado por ámbito de cliente)
  · pide el estado actual al adaptador del transportista del envío
  · aplica reglas: normaliza estado, detecta retraso frente a la fecha estimada, guarda el evento nuevo
        │                                   │
        ▼                                   ▼
last_mile.repository                 integrations/carriers/<transportista>
  · SQL sobre shipments y              · llamada HTTP con timeout
    tracking_events                    · traduce el estado propio a ShipmentStatus
        │                                   │
        ▼                                   ▼
Base de datos                        API del transportista
        │
        ▼
Router → serializa con response_model=TrackingPublic → 200 JSON
Si el servicio lanza ShipmentNotFound → core/errors.py → 404 {"detail": "..."}
Si el transportista no responde → se devuelve el último estado conocido, marcado como no actualizado
```

**Por qué no mezclar responsabilidades:**

- Si el router hablase con UPS, la misma lógica tendría que repetirse en el endpoint público, en el agente de CX y
  en el dashboard de rendimiento.
- Si el servicio construyese SQL, no se podría probar la regla de “retraso” sin base de datos.
- Si el filtro por cliente estuviera en el router, bastaría con olvidarlo en un endpoint nuevo para exponer envíos
  de otra marca (riesgo R1).

---

## 11. Frontend / Backend Separation

### 11.1 Dos sistemas independientes

- **Frontends** (`uis/website`, `uis/backoffice`, futuro portal de tracking): presentación, navegación, estado de
  interfaz y validación orientada a la experiencia de usuario.
- **Backend** (`services/api`): datos, reglas, permisos, integraciones.
- Se comunican **solo por HTTP/JSON** según el contrato OpenAPI. El backend no genera HTML y los frontends no
  acceden a la base de datos ni a las APIs de transportistas.
- Se instalan, construyen, despliegan y reinician por separado. Un despliegue del backoffice no requiere desplegar
  la API, y al revés, mientras el contrato `v1` se mantenga.

### 11.2 Mismo repositorio, proyectos separados

> **Decisión:** mantener el backend en este monorepo (`services/api/`) y no en un repositorio aparte.

- **A favor:** el proyecto transversal ya es un monorepo con proyectos autónomos (sin workspace raíz); los cambios
  que tocan contrato y consumidor pueden ir en una misma PR; el memory bank y `AGENTS.md` sirven a todo el
  sistema.
- **Independencia:** igual que `website` y `backoffice` hoy, `services/api` tendrá sus propias dependencias
  (`pyproject.toml`) y **no compartirá código** con los frontends. El único acoplamiento permitido es el contrato
  HTTP.
- **Repositorios separados** tendrían sentido con equipos distintos o ciclos de despliegue muy distintos; no es el
  caso de un equipo de 7.

### 11.3 URL del backend configurable

Ningún frontend escribe `http://localhost:8000` ni un dominio en el código. Cada frontend tiene **un único
módulo cliente de API** (como ya hace `talent-pipeline-tracker/lib/http.ts`) que lee la URL de una variable de
entorno y falla al arrancar si falta. Los componentes llaman a funciones (`getShipmentTracking(id)`), nunca montan
URLs.

| Quién conoce la URL de la API | Variable | Motivo |
| --- | --- | --- |
| Código de navegador de Next.js (componentes `"use client"`) | `NEXT_PUBLIC_API_BASE_URL` | Next.js solo expone al navegador las variables con este prefijo. |
| Código de servidor de Next.js (Server Components) | `API_BASE_URL` | Solo servidor; permite en el futuro usar una URL interna. |
| Agentes, MCP, workflows, pipelines | `API_BASE_URL` en su propia configuración | Son clientes más de la API. |
| La API | **no** necesita conocer la URL de los frontends, salvo para CORS (`CORS_ALLOWED_ORIGINS`). | |

**Aviso importante del despliegue actual:** Next.js escribe las variables `NEXT_PUBLIC_*` en el bundle **al hacer
`next build`** ([documentación de Next.js](https://nextjs.org/docs/app/guides/environment-variables)). Como hoy
cada app se construye en el servidor, la variable tiene que existir **antes** del build; si se cambia la URL de la
API, hay que reconstruir.

### 11.4 CORS

La API y los frontends viven en **orígenes distintos** (esquema + dominio + puerto): en local, `:3001`/`:3002`
frente a `:8000`; en producción, subdominios distintos. El navegador bloquea esas peticiones salvo que la API
declare los orígenes permitidos.

> **Decisión:** `CORSMiddleware` configurado desde `CORS_ALLOWED_ORIGINS` con una **lista explícita** de orígenes
> (nunca `*`), solo los métodos y cabeceras que se usan (`GET, POST, PUT, PATCH, DELETE`; `Authorization`,
> `Content-Type`), y `allow_credentials` solo si la autenticación acaba usando cookies.

- FastAPI no permite `*` en orígenes, métodos o cabeceras si `allow_credentials=True`, y el navegador rechaza la
  respuesta en ese caso ([FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/),
  [MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)).
- **CORS no es seguridad de la API.** Solo lo aplica el navegador; `curl`, un agente o un script lo ignoran. La
  protección real es la autenticación y la autorización del backend.
- Las peticiones que Next.js hace **desde el servidor** no pasan por CORS. El website (contenido estático) apenas
  necesita la API; el backoffice y el portal de tracking sí harán peticiones desde el navegador.
- **Caso concreto — formulario de leads:** hoy vive en `uis/landing/formulario/` (HTML estático del Hito 1) y
  simula el envío. Conectarlo a `POST /api/v1/leads` exigiría modificar esa app (área protegida en `AGENTS.md`,
  requiere confirmación) y añadir su origen (`https://landingtrackflow.rubenlosada.com`) a `CORS_ALLOWED_ORIGINS`.

**Alternativa considerada:** servir la API bajo el mismo origen de cada frontend mediante un proxy
(`/api` → backend) y evitar CORS. Se descarta como opción por defecto porque hay dos frontends con dominios
distintos y consumidores que no son navegadores; queda disponible si en el futuro se usan cookies de sesión.

### 11.5 Entornos

| | Local | Staging | Producción |
| --- | --- | --- | --- |
| API | `http://localhost:8000` | *Supuesto:* URL de preproducción | *Supuesto:* subdominio propio de `rubenlosada.com` (requiere confirmación: DNS es área protegida en `AGENTS.md`) |
| Website | `http://localhost:3001` | *Supuesto* | `https://websitetrackflow.rubenlosada.com` (hecho) |
| Backoffice | `http://localhost:3002` | *Supuesto* | `https://backofficetrackflow.rubenlosada.com` (hecho) |
| `CORS_ALLOWED_ORIGINS` | los dos orígenes locales | los orígenes de staging | los dos orígenes de producción |
| Base de datos | local (*Supuesto:* PostgreSQL en contenedor, lo que implica un `docker-compose.yml` que requiere confirmación) | gestionada | gestionada, con copias de seguridad |
| Documentación `/docs` | abierta | abierta | *Supuesto:* protegida o desactivada (`openapi_url=None`) |
| Datos | de ejemplo (sin datos reales) | anonimizados | reales |

Hoy **no existe staging** (hecho). La tabla indica dónde encajaría, no que exista.

### 11.6 Variables de entorno (conceptuales)

```text
# services/api (.env.example: sin valores secretos)
APP_ENV=local                     # local | staging | production
DATABASE_URL=...                  # cadena de conexión; nunca en el código
CORS_ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3002
SECRET_KEY=...                    # firma de tokens (cuando haya auth)
LOG_LEVEL=INFO
CARRIER_<NOMBRE>_API_KEY=...      # una por transportista integrado
WMS_LOS_ANGELES_URL=...           # según el adaptador

# uis/backoffice, uis/website (.env.example)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
API_BASE_URL=http://localhost:8000
```

---

## 12. Initial Technical Decisions

| # | ¿Qué proponemos? | ¿Por qué? | ¿Qué problema evita? |
| --- | --- | --- | --- |
| D1 | **FastAPI** en `services/api/`, Python y `pyproject.toml` propio. | Lo fija el repositorio (`README.es.md`) y el curso; validación, OpenAPI e inyección de dependencias integradas. | Frameworks alternativos o un backend dentro de Next.js que mezcle UI y reglas. |
| D2 | **Versionado en ruta `/api/v1`** + `/health` sin versión. | Muchos consumidores que no se despliegan a la vez (dos frontends, agentes, n8n). | Romper a un consumidor al cambiar un contrato. |
| D3 | **Configuración con `pydantic-settings`** en `core/config.py`, leída una vez (`get_settings()` con `lru_cache`) e inyectada como dependencia. | Patrón de la documentación de FastAPI; valida tipos al arrancar y se sustituye fácilmente en tests. | URLs y credenciales en el código; la API arrancando con configuración incompleta. |
| D4 | **Esquemas Pydantic separados de los modelos de tabla**, varios por entidad (`XCreate`, `XUpdate`, `XPublic`) con una base común. | FastAPI recomienda varios modelos por entidad: la entrada, la salida y la tabla no tienen los mismos campos. Ejemplo: el tracking público no debe exponer coste ni cliente; el cliente no decide el `id`. | Filtrar datos internos por la API; que un cambio de tabla rompa el contrato. |
| D5 | **SQLAlchemy 2 + Alembic** sobre una base relacional (*Supuesto:* PostgreSQL). | Los datos son relacionales (envío → cliente, transportista; devolución → envío) y los KPIs son agregaciones. Alembic da migraciones versionadas. *Alternativa considerada:* SQLModel (la usa el tutorial de FastAPI) reduce duplicación, pero une tabla y contrato en la misma clase; se prefiere la separación explícita de D4. | Esquemas cambiados a mano; lógica de agregación reimplementada en cada frontend. |
| D6 | **Sesión por petición** con dependencia `yield` (`SessionDep`). | Patrón documentado por FastAPI; abre y cierra la sesión aunque haya error. | Conexiones que se quedan abiertas; transacciones a medias. |
| D7 | **Dependencias reutilizables como alias `Annotated`** en `api/deps.py` (`CurrentUser`, `ClientScope`, `Pagination`) y dependencias a nivel de router. | Recomendación de FastAPI para bases de código grandes: la regla se declara una vez. | Endpoints que olvidan comprobar permisos o ámbito de cliente. |
| D8 | **Errores:** los servicios lanzan excepciones de dominio; `core/errors.py` las traduce con `exception_handler` al formato estándar `{"detail": ...}`; las validaciones siguen el `422` por defecto. | Mantiene los servicios independientes de HTTP; el formato `detail` ya lo sabe interpretar el cliente HTTP del tracker, que sirve de referencia para los frontends nuevos. | `HTTPException` repartidos por la lógica; respuestas de error distintas en cada endpoint. |
| D9 | **Paginación y filtros en servidor** para listados (`limit`/`offset`, filtros como *query params*). | Envíos y devoluciones crecen sin límite. El tracker hoy descarga 200 registros y filtra en cliente: aceptable allí, no para los envíos de dos almacenes. | Respuestas enormes y lentas; filtrado duplicado en cada frontend. |
| D10 | **Autenticación como requisito antes de datos reales**, aunque no se implemente en la primera fase. Tres audiencias: personal interno (roles por área), usuarios de marca (limitados a su `client_id`), consumidor final (sin login, solo tracking con datos mínimos). Agentes y workflows con credenciales de servicio. *Supuesto arquitectónico:* OAuth2 con token Bearer usando `fastapi.security`, o un proveedor de identidad externo; se decide en su hito. | El backoffice está publicado sin autenticación (hecho); conectarlo a datos reales sin auth expondría información de clientes. | Datos de una marca visibles para otra o para cualquiera en Internet. |
| D11 | **Integraciones detrás de un contrato común** (`integrations/<tipo>/base.py`) con timeouts y normalización al vocabulario de TrackFlow. | 8 transportistas y 2 SGA con formatos distintos; hoy son scripts punto a punto sin documentar. | Que el formato de un tercero se filtre al dominio y a los frontends; que un transportista caído bloquee la API. |
| D12 | **Fechas en UTC (ISO 8601) y moneda explícita.** *Supuesto arquitectónico:* importes como `Decimal` con código de moneda; `packages/shared` solo usa EUR, pero EE. UU. operará previsiblemente en USD. | Dos países, dos zonas horarias (Los Ángeles y Zaragoza) y KPIs comparativos por país. | “Entrega a tiempo” mal calculada por zona horaria; sumar euros y dólares. |
| D13 | **Testing con `pytest` + `TestClient`** y `app.dependency_overrides` para sustituir BD, configuración y usuario. Tests unitarios de reglas puras (aprobación de devoluciones, selección de transportista) sin BD. | Patrón oficial de FastAPI. Hoy el repo no tiene tests: el backend sería el primer proyecto con ellos (acordarlo según `techContext.md`). | Regresiones en reglas de negocio que afectan a clientes. |
| D14 | **OpenAPI como contrato**: `openapi_tags` con descripciones en español, `response_model` en todas las rutas, `/docs` en local y staging. | FastAPI lo genera desde el código; es la documentación que usarán frontends, agentes y MCP. *Futuro:* generar los tipos TypeScript de los frontends a partir de `openapi.json`. | Documentación desincronizada; tipos duplicados a mano en TS y Python. |
| D15 | **Tareas en segundo plano:** `BackgroundTasks` solo para trabajo ligero (enviar una notificación tras responder). Trabajo pesado (clasificación de imágenes, sondeo de 8 transportistas) → un *worker* separado cuando haga falta. Tareas programadas → `workflows/` (n8n) llamando a la API. | FastAPI indica que para cálculo pesado o procesos separados conviene una herramienta mayor. | Peticiones HTTP que tardan minutos; un proceso API saturado por trabajos de fondo. |
| D16 | **Observabilidad mínima desde el día 1:** `/health`, logs estructurados con ID de petición y duración. | El `CONTEXT` describe fallos descubiertos por WhatsApp; el siguiente hito es Telemetría. | Fallos silenciosos; incidencias imposibles de rastrear entre países. |

Deliberadamente **no** se proponen ahora: Celery/colas, caché distribuida, GraphQL, *event sourcing*, Kubernetes
ni un API gateway. Ninguno responde a un problema actual del `CONTEXT`.

---

## 13. Risks and Points of Attention

### R1. Una marca ve datos de otra

1. **Qué podría salir mal:** un endpoint nuevo de envíos o devoluciones devuelve registros de otras marcas.
2. **Por qué:** el filtro por `client_id` se escribe a mano en cada consulta y se olvida en una.
3. **Impacto:** crítico. Incumplimiento de contrato y confidencialidad; las renovaciones “se ganan o se pierden” por
   la confianza (`CONTEXT`).
4. **Mitigación:** dependencia `ClientScope` obligatoria en los routers con datos de marca; los métodos de
   repositorio reciben el ámbito como parámetro obligatorio; tests por endpoint con dos marcas distintas.

### R2. Lógica de negocio en routers o duplicada entre capas

1. **Qué podría salir mal:** la regla de aprobación de devoluciones aparece en un router, en el backoffice y en el
   agente de CX, con tres versiones distintas.
2. **Por qué:** es más rápido escribir un `if` en el endpoint; además ya existen reglas en TypeScript
   (`packages/shared/utils/validations.ts`) y en el formulario del Hito 1 que habrá que llevar a Python.
3. **Impacto:** decisiones distintas según el canal; errores difíciles de rastrear.
4. **Mitigación:** las reglas viven solo en `domains/<d>/service.py`; los routers no tienen `if` de negocio (se
   revisa en code review); la validación del frontend se limita a la experiencia de usuario; al portar las reglas de
   `packages/shared`, se documenta que el backend pasa a ser la fuente de verdad. `packages/shared` no se modifica
   (lo usan hitos anteriores).

### R3. Acoplamiento a transportistas y SGA

1. **Qué podría salir mal:** códigos de estado de UPS o columnas de la hoja de cálculo de Zaragoza aparecen en los
   esquemas de la API o en el frontend; una API de transportista lenta bloquea el tracking.
2. **Por qué:** es tentador devolver “lo que dice el transportista” tal cual.
3. **Impacto:** cada cambio de un tercero obliga a tocar dominio y frontends; reproduce el “patchwork” actual.
4. **Mitigación:** contrato común en `integrations/`; traducción a `ShipmentStatus`; timeouts; devolver el último
   estado conocido si el tercero falla; tests del adaptador con respuestas de ejemplo.

### R4. Configuración codificada y CORS mal configurado

1. **Qué podría salir mal:** `allow_origins=["*"]` “para que funcione”; el backoffice de producción apuntando a
   `localhost:8000`; una clave de transportista en un commit.
2. **Por qué:** prisa en local; `NEXT_PUBLIC_*` se fija en el build y el build se hace en el servidor.
3. **Impacto:** fallo total del frontend en producción, o exposición de credenciales.
4. **Mitigación:** `CORS_ALLOWED_ORIGINS` explícito por entorno; la API y los frontends no arrancan si falta una
   variable obligatoria (como ya hace el tracker); solo se versiona `.env.example` (regla de `AGENTS.md`);
   comprobación de la URL de la API en la validación de despliegue.

### R5. Conectar el backoffice a datos reales sin autenticación

1. **Qué podría salir mal:** el backoffice, hoy público y sin login, empieza a mostrar clientes, contratos o envíos
   reales.
2. **Por qué:** la API funciona y conectar el frontend es el paso “natural”.
3. **Impacto:** exposición de datos comerciales y personales (direcciones de consumidores).
4. **Mitigación:** la API exige autenticación en todos los routers internos **desde el primer endpoint con datos
   reales**, independientemente de lo que haga el frontend; CORS no se considera control de acceso; el endpoint
   público de tracking devuelve solo campos mínimos.

### R6. Límites entre dominios que se diluyen

1. **Qué podría salir mal:** `reverse_logistics` importa el modelo `Shipment`; `reporting` lanza SQL sobre las
   tablas de todos los dominios; el monolito modular se convierte en un monolito acoplado.
2. **Por qué:** dentro del mismo proceso, todo se puede importar.
3. **Impacto:** cambiar una tabla rompe dominios ajenos; extraer un servicio en el futuro se vuelve inviable.
4. **Mitigación:** reglas de §5.4 (solo se importa `service` de otros dominios); revisión en PR;
   *opcional futuro:* comprobación automática de imports cuando exista CI (requiere confirmación).

---

## 14. Trade-offs

| Sacrificamos | Por qué lo aceptamos |
| --- | --- |
| **Más ficheros por funcionalidad:** un endpoint sencillo (p. ej. `POST /leads`) toca router, esquema, servicio, repositorio y modelo. | El coste es fijo y pequeño; a cambio, las funcionalidades complejas (devoluciones, tracking) tienen un sitio claro. Para dominios muy simples se permite que el servicio sea mínimo, pero no que el router acceda a la BD. |
| **Duplicación aparente entre modelos y esquemas** (SQLAlchemy + Pydantic). | Es la separación que protege el contrato (D4). Se reduce con clases base comunes. |
| **Disciplina del equipo:** las reglas entre dominios no las impone el lenguaje. | Es más barata que operar microservicios. Se refuerza con revisión y, más adelante, con comprobaciones automáticas. |
| **Un único punto de fallo:** si la API cae, caen todos los consumidores, incluido el tracking 24/7. | Mitigado con varios *workers*, `/health` y, si hiciera falta, extrayendo el tracking público (§15). Hoy no hay datos que justifiquen más. |
| **No se escala un dominio por separado.** | Con el volumen supuesto no es necesario; escalar el proceso completo es suficiente. |
| **Dos lenguajes** (TypeScript en frontends, Python en backend): tipos duplicados. | Lo marca el curso y el repo. OpenAPI es la fuente de verdad y permite generar tipos TS más adelante. |
| **Estructura que hoy parece excesiva** para 3 dominios iniciales. | Los hitos siguientes (Telemetría, RAG, Agentes, Workflows, Tiempo real) añadirán consumidores y capacidades. Reorganizar un backend ya en producción cuesta más que empezar ordenado. |

---

## 15. Future Evolution

```text
Fase 1 — Monolito modular mínimo
  services/api con core, /health, commercial (leads, clients), last_mile (carriers, shipments),
  reverse_logistics (returns). Entidades ya modeladas en packages/shared. BD y migraciones.
        ↓
Fase 2 — Integraciones y seguridad
  Autenticación (antes de datos reales en el backoffice), adaptadores de transportistas,
  tracking unificado y público, reglas de aprobación de devoluciones, selección de transportista.
        ↓
Fase 3 — Almacén, CX y dirección
  Adaptadores de los dos SGA → warehouse (inventario unificado, pedidos); customer_service (tickets);
  reporting (KPIs, informe semanal vía workflows/). Agentes y MCP consumen la API.
        ↓
Fase 4 — Procesos separados solo donde haya necesidad medida
  Worker para trabajo pesado (inspección por imagen, sondeo de transportistas);
  tiempo real (WebSockets/SSE en la misma app); vistas de lectura para reporting.
        ↓
Fase 5 — Servicio independiente, solo si se cumple algún criterio de extracción
```

**Criterios para extraer un dominio a un servicio propio** (hoy no se cumple ninguno):

- Su carga es muy distinta al resto y afecta a los demás (candidato natural: el **tracking público**, que atiende a
  consumidores 24/7).
- Necesita un ciclo de despliegue o un equipo propios.
- Tiene requisitos de disponibilidad o seguridad incompatibles con el resto.

Gracias a las reglas de §5.4 (un dominio solo expone su servicio y solo toca sus tablas), la extracción consistiría
en sustituir llamadas a `service` por llamadas HTTP, no en reescribir el dominio. **No se afirma que vaya a haber
microservicios:** el `CONTEXT` no lo justifica hoy.

---

## 16. Conclusion

TrackFlow necesita, antes que nada, **un lugar único y ordenado** donde vivan sus datos operativos y sus reglas:
hoy están repartidos entre dos SGA, un ERP, hojas de cálculo, scripts y documentos de Word. Un monolito modular en
FastAPI, organizado por las mismas áreas que describe el `CONTEXT` y con capas claras dentro de cada una, ofrece
eso con el menor coste operativo posible para un equipo de siete personas. Además, deja preparada la evolución que
piden los siguientes hitos sin comprometerse con una arquitectura distribuida que hoy no se justifica.

**Siguiente paso propuesto:** validar con el CTO los supuestos marcados en este documento (base de datos,
dominio de la API, entorno de staging, autenticación, moneda) y, tras su aprobación, crear el esqueleto de la
fase 1 en `services/api/`.

### Correspondencia con la documentación de FastAPI

| Elemento de la propuesta | Práctica de FastAPI en la que se basa |
| --- | --- |
| Un `APIRouter` por recurso, `include_router` en un router agregador y en `main.py` | *Bigger Applications*: `APIRouter` como “mini FastAPI”, con `prefix`, `tags`, `dependencies` y `responses` por router. |
| `prefix` sin barra final; dependencias a nivel de router | *Bigger Applications*: el prefijo no debe terminar en `/`; las dependencias del router se ejecutan antes que las del decorador. |
| `pyproject.toml` con `[tool.fastapi] entrypoint` | *Bigger Applications*: recomendación de declarar el *entrypoint*. |
| `core/config.py` con `pydantic-settings` y `get_settings()` con `lru_cache` | *Settings and Environment Variables*. |
| Alias `Annotated` en `api/deps.py`, sub-dependencias (`CurrentUser` → `ClientScope`) | *Dependencies*: reutilización con `Annotated` y dependencias anidadas. |
| `SessionDep` con `yield` | *SQL (Relational) Databases*: una sesión por petición. |
| Esquemas `Create`/`Update`/`Public` separados del modelo de tabla | *Extra Models* y *SQL Databases* (varios modelos por entidad). |
| Excepciones de dominio traducidas con `exception_handler`; formato `detail` y `422` por defecto | *Handling Errors*. |
| `TestClient` + `dependency_overrides` | *Testing* y *Settings* (override en tests). |
| `CORSMiddleware` con orígenes explícitos | *CORS*. |
| `openapi_tags`, `/docs` desactivable con `openapi_url=None` | *Metadata and Docs URLs*. |
| `BackgroundTasks` solo para trabajo ligero | *Background Tasks* (recomienda herramientas mayores para cálculo pesado). |
| Organización tipo `api/`, `api/deps.py`, `core/config.py` | *Full Stack FastAPI Template*. Diferencia: la plantilla agrupa todos los modelos en `models.py` y la persistencia en `crud.py`; aquí se reparten por dominio porque TrackFlow tiene 6 dominios, no 2 recursos. |

---

## 17. References

**FastAPI (documentación oficial)**

- Bigger Applications — Multiple Files: <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- Dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- Settings and Environment Variables: <https://fastapi.tiangolo.com/advanced/settings/>
- SQL (Relational) Databases: <https://fastapi.tiangolo.com/tutorial/sql-databases/>
- Extra Models: <https://fastapi.tiangolo.com/tutorial/extra-models/>
- Handling Errors: <https://fastapi.tiangolo.com/tutorial/handling-errors/>
- Testing: <https://fastapi.tiangolo.com/tutorial/testing/>
- CORS (Cross-Origin Resource Sharing): <https://fastapi.tiangolo.com/tutorial/cors/>
- Metadata and Docs URLs: <https://fastapi.tiangolo.com/tutorial/metadata/>
- Security — intro: <https://fastapi.tiangolo.com/tutorial/security/>
- Background Tasks: <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- Full Stack FastAPI Template: <https://github.com/fastapi/full-stack-fastapi-template>

**Frontend/backend desacoplados, configuración y CORS**

- MDN — Cross-Origin Resource Sharing (CORS): <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS>
- Next.js — Environment Variables: <https://nextjs.org/docs/app/guides/environment-variables>
- The Twelve-Factor App — III. Config: <https://12factor.net/config>

**Arquitectura**

- Martin Fowler — MonolithFirst: <https://martinfowler.com/bliki/MonolithFirst.html>

**Repositorio (contexto)**

- [`CONTEXT.es.md`](../CONTEXT.es.md), [`CONTEXT-trackflow.es.md`](../CONTEXT-trackflow.es.md)
- [`memory-bank/projectbrief.md`](../memory-bank/projectbrief.md), [`memory-bank/techContext.md`](../memory-bank/techContext.md), [`memory-bank/progress.md`](../memory-bank/progress.md)
- [`packages/shared/types/models.ts`](../packages/shared/types/models.ts), [`packages/shared/utils/validations.ts`](../packages/shared/utils/validations.ts)
- [`uis/backoffice/lib/data/initiatives.ts`](../uis/backoffice/lib/data/initiatives.ts), [`uis/talent-pipeline-tracker/lib/http.ts`](../uis/talent-pipeline-tracker/lib/http.ts)
- [`README.es.md`](../README.es.md) (definición de `services/`)
