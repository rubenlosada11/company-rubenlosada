# Project Brief — TrackFlow

> Síntesis para agentes. Fuente de verdad del negocio: [`CONTEXT.es.md`](../CONTEXT.es.md) (briefing general de la
> empresa) y [`CONTEXT-trackflow.es.md`](../CONTEXT-trackflow.es.md) (detalle de los hitos 1 y 2: contenido de la
> web, contacto, formulario). Si algo de este resumen contradice esos ficheros, **manda el CONTEXT** y este fichero
> se corrige.
>
> **Nota:** en la raíz **no existe `CONTEXT.md`**. Tras el commit `9881b2a` (eliminación de versiones en inglés) el
> contexto vive en `CONTEXT.es.md`. No crear un `CONTEXT.md` duplicado.

## Empresa

**TrackFlow** — empresa de logística de última milla y gestión de almacenes fundada en **2009** en **Los Ángeles**
(EE. UU.). Opera en dos mercados, **Estados Unidos y España**, con almacenes en **Los Ángeles y Zaragoza**.
Aprox. **130 empleados** y aprox. **9 M€** de facturación anual.

Nuestra posición: trabajamos en **TrackFlow Tech**, la unidad interna creada para construir los sistemas,
integraciones y automatizaciones inteligentes que permitan a TrackFlow operar a escala en dos países. El CTO
(**Andrés Kim**, Zaragoza) es nuestro responsable directo; el stakeholder del sitio público es **Miguel Torres**
(Director Comercial).

## Qué hace (servicios)

1. **Gestión de almacenes** — almacenamiento, picking y packing, inventario.
2. **Entregas de última milla** — red de transportistas en ambos países, seguimiento, gestión de incidencias.
3. **Logística inversa** — devoluciones, inspección y reacondicionamiento.

Cobertura: EE. UU. (almacén en Los Ángeles; UPS, FedEx, DHL) y España (almacén en Zaragoza; MRW, SEUR, DHL).
En total **8 transportistas** (incluye 2 locales sin nombre en el CONTEXT).

## Problema que aborda

- **Para los clientes:** las marcas de e-commerce saben fabricar y vender, no hacer llegar el producto a la puerta
  del cliente. TrackFlow asume toda la operación logística, desde el pedido hasta la entrega o devolución.
- **Internamente (el motivo de TrackFlow Tech):** falta infraestructura para operar en dos países a escala.
  Dos sistemas de almacén sin inventario compartido, sin datos estructurados de rendimiento de transportistas,
  devoluciones aprobadas una a una (18–25 % del volumen), consultas de cliente repetitivas respondidas a mano
  (~80 % automatizables), informe semanal del CEO ensamblado manualmente, arquitectura tecnológica “patchwork”
  sin telemetría.

## Para quién

- **B2B (público del website):** marcas de e-commerce **medianas** de **moda, electrónica y cosmética** que quieren
  externalizar su logística. *No* es para consumidores finales que quieren rastrear un paquete o devolver algo.
- **Consumidores finales (B2C):** destinatarios de los paquetes (necesitan seguimiento; portal público de
  tracking = necesidad identificada, no construida).
- **Usuarios internos (público del backoffice):** equipos de operaciones, última milla, logística inversa,
  atención al cliente, comercial, tecnología y dirección.

## Áreas de la empresa (datos del CONTEXT)

| Área | Responsable | Equipo |
| --- | --- | --- |
| Operaciones de almacén | Ana Whitfield | ~70 operarios + 2 responsables de almacén |
| Última milla y transportistas | Carlos Vega | 6 coordinadores logísticos |
| Logística inversa | Sofía Ramos | 5 personas |
| Experiencia del cliente | Valentina Cruz | 15 agentes (LA + Zaragoza) |
| Comercial y relación con clientes | Miguel Torres | 4 account managers + 4 desarrollo de negocio |
| Tecnología | Andrés Kim | 7 personas (Zaragoza) |
| Dirección ejecutiva | Thomas Harry, fundador y CEO (ver inconsistencias) | Directores de área |

## Objetivos

- **Negocio (CONTEXT):** que TrackFlow deje de ser lenta, propensa a errores y poco rentable por falta de
  sistemas: inventario unificado, datos de transportistas, devoluciones automatizadas, CX automatizada, visión
  ejecutiva en tiempo real, telemetría central.
- **Proyecto transversal (4Geeks AI Engineering):** construir *una sola empresa* a lo largo de varios hitos
  (Web, Programación, Backend, Telemetría, RAG, Agentes, Workflows, Tiempo real — ver `README.es.md`).

## Alcance del proyecto actual — Hito 4 “Ingeniería impulsada por IA”

Dejar el monorepo **AI-ready** y con la estructura inicial de aplicación:

- `memory-bank/` (este directorio), `AGENTS.md`, `.agents/rules/`, `.agents/skills/`.
- `uis/website` — web corporativa pública.
- `uis/backoffice` — aplicación interna con layout propio.
- `services/` **solo si hace falta**: no se crea backend (las dos apps son estáticas sobre datos del CONTEXT).
- Rama `feature/agent-memory-bank` → Pull Request a `main`.

**Fuera de alcance:** modificar las apps de hitos anteriores, backend, autenticación real, integraciones con
sistemas reales, datos en vivo, métricas inventadas.

## Relación con el roadmap

El CONTEXT **no** define un roadmap fechado. El roadmap implícito son (a) las *necesidades por área* del CONTEXT
(qué necesita cada departamento) y (b) los hitos del curso. Este hito es la **base de infraestructura**: el
memory bank y `AGENTS.md` permiten que sesiones futuras de agentes construyan las necesidades de cada área
(API de inventario, motor de transportistas, agente de CX, dashboards, telemetría…) sin perder contexto, y las
dos apps son el punto de entrada visual (público e interno) sobre el que se irán integrando.

## Reglas de contenido (derivadas del CONTEXT)

- No inventar clientes, logos, certificaciones, premios ni cifras. Cifras permitidas: las que figuran en el
  CONTEXT (2009, ~130 empleados, ~9 M€ de facturación anual, 2 países, 2 almacenes, 8 transportistas, 18–25 %
  devoluciones, ~80 % consultas automatizables, tamaños de equipo). La facturación (~9 M€) **se publica** en el
  website y en el backoffice (decisión del desarrollador, 2026-09-22).
- Todo es un **ejercicio ficticio de bootcamp**: no hace falta validar el copy con el stakeholder (Miguel Torres) ni
  contrastar cada claim con la realidad.
- El sitio público se dirige a **marcas de e-commerce**, no a consumidores finales.
- Idioma base de todo el proyecto: **español**. Segundo idioma (inglés) = mejora opcional futura.
- Datos de contacto públicos (de `CONTEXT-trackflow.es.md`): `comercial@trackflow.com`, +1 213 555 0147
  (Los Ángeles), +34 976 123 456 (Zaragoza), LinkedIn `https://linkedin.com/company/trackflow`.
- Captación de leads: ya existe el formulario en `uis/landing/formulario/` (no duplicarlo).

## Inconsistencias conocidas del CONTEXT (no editar el CONTEXT sin confirmación)

1. **Nombre del CEO — RESUELTO (2026-09-22): Thomas Harry.** `CONTEXT.es.md` dice “Thomas Harry, fundador y CEO”
   (líneas 29 y 45) pero también “CEO: Daniel Espinoza” y “Daniel ha creado TrackFlow Tech” (líneas 53, 123 y 125).
   El desarrollador decidió usar **Thomas Harry**; así aparece en el backoffice. El CONTEXT no se ha modificado,
   por lo que sigue nombrando a Daniel: no “corregir” la UI a Daniel sin confirmación.
2. **Claims de marketing vs. realidad técnica — ACEPTADO:** el briefing del Hito 1 pide copy como “inventario en
   tiempo real” y “tecnología propia para visibilidad total”, mientras `CONTEXT.es.md` indica que hoy los dos
   almacenes **no** comparten inventario. El website mantiene el copy del stakeholder; por ser un ejercicio
   ficticio de bootcamp, el desarrollador indicó que no hace falta revisión.
3. **Transportistas locales:** el CONTEXT habla de “dos transportistas locales” sin nombre; `packages/shared`
   usa nombres de ejemplo (QuickShip Local, LocalExpress). No usarlos en UIs públicas.
