# AUDIT.md — Auditoría de rendimiento de los frontends

Diagnóstico inicial de la auditoría de rendimiento de los dos frontends de TrackFlow (práctica sin número de hito,
rama `feature/frontend-performance-audit`, 2026-11-02). Los resultados, la comparativa antes/después y el impacto de
cada corrección están en [`REPORT.md`](./REPORT.md). Evidencias y procedimiento de medición: [`audit/`](./audit/README.md).

Ciclo seguido: **medir → analizar → corregir → validar → documentar**. Ninguna cifra de este documento es una
estimación propia: todas salen de los informes de Lighthouse versionados en `audit/before/`.

## 1. Objetivo y alcance

Encontrar lo que de verdad frena a los dos frontends, corregir la causa y demostrar el efecto con mediciones
comparables, **sin reestructurar nada**: mismos frameworks, rutas, modelo de sesión, contratos con la API y
comportamiento.

| Aplicación | Carpeta | Qué es |
| --- | --- | --- |
| Sitio corporativo (*corporate*) | `uis/website` | Web pública para marcas de e-commerce. Una sola página (`/`), estática (SSG). |
| Backoffice | `uis/backoffice` | Panel interno con login JWT. El panel se pinta en el cliente tras validar la sesión contra `services/api`. |

Ambas: Next.js 16.3.4 (App Router, Turbopack), React 19.2.8, Tailwind CSS 4, TypeScript estricto, fuentes con
`next/font/google` (Archivo + Manrope), npm con lockfile por app, sin workspace raíz. El backoffice necesita la API
(`services/api`, FastAPI) para el login y para todas las vistas salvo el dashboard, cuyos datos son estáticos
(`lib/data/`). Fuera de alcance: las apps de hitos anteriores (`landing`, `script-automatizacion`,
`talent-pipeline-tracker`), `packages/` y la API.

## 2. Metodología y entorno

| Pieza | Valor |
| --- | --- |
| Builds | `npm run build` + `npm run start` (producción). Website `:3001`, backoffice `:3002`. Nunca `next dev`. |
| API | `services/api` en `:8000` con copias de las bases y un usuario propio de la auditoría (no toca datos reales ni Supabase) |
| Lighthouse | 12.8.2 por API de Node; configuración por defecto (móvil) y `desktop-config` (escritorio) |
| Navegador | Chrome 156.0.8078.74, `--headless=new`, perfil nuevo en cada ejecución |
| Throttling | Simulado. Móvil: 412×823 DPR 1,75, RTT 150 ms, 1,6 Mbps, CPU ×4. Escritorio: 1350×940, RTT 40 ms, 10 Mbps, CPU ×1 |
| Equipo | Windows 11 Pro, Node 24.19.0 (`benchmarkIndex` ≈ 2000–3150) |
| Repeticiones | 5 por página y dispositivo. Tablas con la **mediana de cada métrica**; se versiona la ejecución mediana de Lighthouse (`computeMedianRun`) |

### URLs auditadas

| Aplicación | URL | Dispositivos | Por qué |
| --- | --- | --- | --- |
| Corporate | `/` | escritorio y móvil | Única página de contenido del sitio (además de la 404). |
| Backoffice | `/` (dashboard) | escritorio y móvil | Página principal obligatoria. Móvil también: el panel tiene navegación móvil propia y se usa en terminales del almacén. |
| Backoffice | `/gestor-incidencias` | escritorio | La vista más pesada con datos reales: 5 tarjetas, 3 gráficos de barras y una tabla de 95 incidencias con 4 filtros. |

### Datos de campo (CrUX)

**No hay datos de campo.** Las mediciones son en `localhost`, que no tiene CrUX. Para las demos públicas
(`websitetrackflow.rubenlosada.com`, `backofficetrackflow.rubenlosada.com`) se intentó consultar la API de PageSpeed
Insights el 2026-11-02 y devolvió *quota exceeded* (cuota anónima agotada); además, son subdominios con muy poco
tráfico y el backoffice publicado está tras autenticación, así que es muy probable que CrUX no tenga muestras
(hipótesis no comprobada). Por eso **INP no se puede medir** aquí: Lighthouse en modo navegación no tiene
interacciones. TBT se usa solo como indicador de laboratorio del bloqueo del hilo principal, **no** como INP.

## 3. Puntuaciones iniciales (BEFORE)

Mediana de 5 ejecuciones. Evidencias: `audit/before/<app>/<página>-<dispositivo>.{html,json,png}` y
`audit/before/runs.json`.

| Página | Perf. | Acc. | BP | SEO | FCP | LCP | TBT | CLS | SI | TTFB | Peso | Peticiones |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| corporate · home · desktop | 100 | 96 | 100 | 100 | 220 ms | 561 ms | 2 ms | 0.000 | 330 ms | 6 ms | 266 KiB | 12 |
| corporate · home · mobile | 96 | 96 | 100 | 100 | 767 ms | **2639 ms** | 106 ms | 0.000 | 865 ms | 6 ms | 273 KiB | 12 |
| backoffice · dashboard · desktop | 100 | 96 | 100 | 63 | 218 ms | 768 ms | 2 ms | 0.000 | 316 ms | 5 ms | 314 KiB | 44 |
| backoffice · dashboard · mobile | 93 | 96 | 100 | 63 | 765 ms | **3056 ms** | 133 ms | 0.000 | 765 ms | 5 ms | 266 KiB | 26 |
| backoffice · gestor-incidencias · desktop | 95 | 100 | 100 | 63 | 214 ms | 842 ms | 0 ms | **0.133** | 336 ms | 4 ms | 342 KiB | 48 |

Variabilidad: escritorio estable (±1 punto). En el dashboard móvil una de las cinco ejecuciones dio 85 (TBT 380 ms)
frente a 92–94 en las demás; en una prueba previa, no incluida, dio 68. La mediana absorbe esos valores atípicos.

### Core Web Vitals (laboratorio)

| Página | LCP (≤ 2,5 s) | CLS (≤ 0,1) | INP | TBT (lab, ≤ 200 ms) |
| --- | --- | --- | --- | --- |
| corporate · móvil | 2,64 s — **mejorable** | 0 | sin datos | 106 ms |
| backoffice · dashboard · móvil | 3,06 s — **mejorable** | 0 | sin datos | 133 ms |
| backoffice · gestor · escritorio | 0,84 s | 0,133 — **mejorable** | sin datos | 0 ms |
| resto | < 0,8 s | 0 | sin datos | ≤ 2 ms |

**TTFB (4–6 ms):** es `localhost`, sin red real; no representa producción (Cloudflare delante). No hay ningún
problema de respuesta del servidor que atacar en este entorno.

## 4. Problemas detectados

Estado: **confirmado** (lo prueban el informe y el código), **hipótesis** (requiere medir el cambio) o
**secundario** (se documenta, no se corrige).

### Sitio corporativo (`uis/website`)

| ID | Problema | Evidencia (Lighthouse) | Causa raíz | Efecto en el usuario | Corrección propuesta | Riesgo | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W1 | LCP móvil 2,64 s; el LCP es la imagen del hero | `largest-contentful-paint-element`: `figure > img` del hero; fases: TTFB 459 ms + *render delay* 2180 ms (83 %). `lcp-discovery-insight`: «fetchpriority=high should be applied» ✗ | En Next 16 la prop `priority` de `next/image` (obsoleta) solo emite un `<link rel="preload">` **sin** `fetchpriority`; el navegador trata la imagen como prioridad baja hasta el layout y compite con el logo, también precargado. | En móvil, la imagen principal aparece tarde. | `fetchPriority="high"` y `preload` en la imagen del hero (sustituye a `priority`). | Bajo | Confirmado |
| W2 | Logo de la cabecera pedido a 1200/3840 px y precargado | `total-byte-weight`: `_next/image?url=…Logo…&w=3840`. HTML: `<link rel="preload" as="image" imageSrcSet="…w=1200 1x, …w=3840 2x">` | `<Image width={1190}>` sin `sizes`: Next genera candidatos 1x/2x según el ancho intrínseco (1190 px) aunque se pinta a ≤ 180 px. Además `priority` añade un segundo preload que compite con el LCP. | Bytes y ancho de banda gastados antes del LCP. | `sizes` según el tamaño real, carga `eager` sin preload. | Bajo | Confirmado |
| W3 | Imagen del hero mayor de lo necesario | `image-delivery-insight`: 750×409 servida para 377×206 mostrados, ahorro estimado 29 KiB | El cálculo usa píxeles CSS; con DPR 1,75 hacen falta ~660 px y el candidato más próximo de `deviceSizes` es 750. El tamaño es correcto; lo que sí se puede ganar es formato (hoy WebP). | Menos bytes en la imagen LCP. | Activar AVIF (`images.formats`) y medir. | Bajo (primera codificación AVIF más lenta en el servidor; queda en caché) | Hipótesis |
| W4 | Accesibilidad 96: contraste insuficiente | `color-contrast`: 4 `<span class="… text-blue-200" aria-hidden>` (números 01–04 del proceso), contraste 1,41:1 (mínimo 3:1, texto grande) | Color decorativo demasiado claro (`blue-200`) en `components/Process.tsx`. | Números ilegibles con baja visión; resta puntos de accesibilidad. | Color con contraste ≥ 3:1. | Mínimo (cambio visual) | Confirmado |
| W5 | JS sin usar (54 KiB) y CSS bloqueante (7 KiB) | `unused-javascript` en los chunks del framework; `render-blocking-insight` 70 ms (el audit clásico estima 0 ms) | Runtime de React/Next, común a cualquier app App Router; CSS de Tailwind ya mínimo. | Bajo. | Ninguna: `experimental.inlineCss` es experimental y reducir el runtime exigiría cambiar de arquitectura. | — | Secundario |

### Backoffice (`uis/backoffice`)

| ID | Problema | Evidencia (Lighthouse) | Causa raíz | Efecto en el usuario | Corrección propuesta | Riesgo | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | LCP móvil del dashboard 3,06 s | LCP = `header > p` del dashboard; *render delay* 2598 ms (85 %). Cascada: JS → `OPTIONS` + `GET http://localhost:8000/auth/me` → render del panel. `uses-rel-preconnect`: `http://localhost:8000`, ahorro estimado 150 ms | El panel solo se pinta cuando `AuthGate` confirma la sesión con `GET /auth/me`, y la API está en **otro origen** que el navegador descubre tarde (cuando ya se ejecutó el JS): conexión nueva + preflight CORS. | El panel tarda más en aparecer, sobre todo en móvil. | `preconnect` (con `crossorigin`) al origen de `NEXT_PUBLIC_API_BASE_URL` en el layout raíz. | Bajo | Confirmado |
| B1b | El contenido depende de una petición a la API | Mismo informe: el HTML inicial solo contiene «Comprobando tu sesión…» | Modelo de sesión de AUTH-02: token en `localStorage`, sin cookies ni middleware. | — | Ninguna en esta auditoría: requiere cambiar el modelo de sesión (cookie + comprobación en servidor). | Alto | Secundario (recomendación) |
| B2 | CLS 0,133 en `/gestor-incidencias` | `layout-shifts`: `section#listado` desplazada (0,133) en las 5 ejecuciones | `IncidentSummary` muestra una línea «Cargando resumen…» y la sustituye por 5 tarjetas y 3 gráficos: el listado de debajo salta. | La tabla se mueve mientras se lee o se va a pulsar. | Durante la primera carga, pintar la misma estructura (tarjetas y barras con «—» y las categorías conocidas) para reservar el alto exacto. | Bajo | Confirmado |
| B3 | Logo pedido a 3840 px y precargado aunque está oculto | `total-byte-weight` (móvil): `_next/image?url=…Logo…&w=3840`. El logo del sidebar (`hidden lg:flex`) lleva `priority` | Igual que W2: sin `sizes`; y el preload del sidebar se descarga también en móvil, donde el sidebar no se ve. | Bytes y una petición prioritaria que compite con la carga inicial. | `sizes` en los logos del backoffice y sin `priority` en el del sidebar. | Bajo | Confirmado |
| B4 | Accesibilidad 96 en el dashboard | `color-contrast`: `h3`/`p` con `text-slate-500` sobre `bg-slate-100`: 4,34:1 (mínimo 4,5:1) | Etiquetas de sección del dashboard (`Overview`, `Explorer`) en gris claro sobre el fondo gris de la página. | Texto pequeño poco legible. | `text-slate-600` en esos textos. | Mínimo | Confirmado |
| B5 | SEO 63 | `is-crawlable`: `<meta name="robots" content="noindex, nofollow">` | Decisión deliberada: herramienta interna que no debe indexarse. | Ninguno. | **No se corrige.** | — | Intencionado |
| B6 | JS sin usar (26 KiB) y tarea larga de hidratación (194 ms en móvil) | `unused-javascript`, `long-tasks` | Runtime de React/Next y render del panel completo tras el login. TBT mediano 133 ms (bueno). | Bajo. | Ninguna sin evidencia de interacción lenta. | — | Secundario |
| B7 | Tabla de 95 incidencias sin paginar (página de 10 500 px) | `layout-shifts`: alto de `section#listado` | La API no pagina (contrato existente). TBT 0 ms en escritorio con el volumen actual. | Ninguno medible hoy. | Ninguna (sería especulativa); revisar si crece el volumen. | — | Secundario |

## 5. Inspección del código

Además de lo anterior (W1–W4, B1–B4), revisado sin hallazgos que justifiquen cambios:

- **Imágenes:** todas con `next/image`, `width`/`height` y `alt`; sin `<img>` sueltos. CLS 0 en el website.
- **Fuentes:** `next/font/google` autoalojadas, `display: swap` por defecto, dos ficheros woff2 precargados
  (`font-display-insight` sin incidencias).
- **Componentes cliente:** website solo `MobileNav`; backoffice, las vistas con estado (filtros, formularios, sesión).
  El dashboard usa `useMemo` donde filtra; sin efectos que encadenen renders.
- **Peticiones:** cada vista hace una petición por cambio de filtro y la cancela (`AbortController`) al cambiar; sin
  peticiones repetidas en la carga. Las peticiones `?_rsc=` del dashboard son el *prefetch* de los enlaces visibles de
  `next/link`, posteriores al LCP.
- **Dependencias:** ninguna librería de terceros en el cliente (solo React y Next).

## 6. Análisis de duplicidades

### D1 — Petición con clave, cancelación y estados de carga/error (6 copias)

| | |
| --- | --- |
| Archivos | `components/gestor-incidencias/IncidentList.tsx`, `IncidentSummary.tsx`, `components/SupplierDirectory.tsx`, `components/inventory/MovementHistory.tsx`, `ProductList.tsx` y `useProducts` en `formParts.tsx` |
| Qué se repite | `useState` de un `result` `{ key, datos, error }`, `requestKey` con los filtros y un contador de recarga, `loading = result?.key !== requestKey`, `useEffect` con `AbortController`, `.then(setResult…)`, `.catch` que ignora la cancelación y traduce el error, y `return () => controller.abort()`. |
| Problema de mantenimiento | Seis implementaciones del mismo contrato con pequeñas diferencias (unas conservan los datos al fallar, otras no); un arreglo en una no llega a las demás. `ProductList` reimplementa entero `useProducts`. |
| Coste de rendimiento | No medible en Lighthouse: hoy todas cancelan bien. El valor es que la cancelación de peticiones obsoletas y la regla «no mostrar respuestas viejas» queden en un solo sitio. |
| Abstracción | Hook tipado `useApiRequest<T>(key, request, errorMessage, opciones)` en `lib/useApiRequest.ts`: devuelve `data`, `error`, `loading`, `loaded`, `reload` y `update` (para los cambios optimistas de filas). |
| Archivos a modificar | Los seis anteriores + el hook nuevo. |

### D2 — Aviso de error con «Reintentar» (5 copias)

| | |
| --- | --- |
| Archivos | `IncidentList.tsx`, `IncidentSummary.tsx`, `SupplierDirectory.tsx`, `MovementHistory.tsx`, `ProductList.tsx` |
| Qué se repite | `<div role="alert" class="rounded-2xl border-red-200 bg-red-50 …">` + título en negrita + mensaje + botón «Reintentar» con las mismas clases (en proveedores, con otro alto). |
| Problema de mantenimiento | Mismo bloque de marcado y accesibilidad copiado; el botón ya ha divergido (sin `min-h-11` en proveedores, por debajo de los 44 px táctiles). |
| Coste de rendimiento | Ninguno medible. |
| Abstracción | Componente `components/LoadErrorAlert.tsx` (`title`, `children` para el detalle, `onRetry`). |
| Archivos a modificar | Los cinco anteriores + el componente nuevo. |

## 7. Skills de rendimiento consultadas

Se leyeron las tres skills indicadas por el CTO directamente de sus repositorios (no se instalaron en el repo ni en
la configuración global: se usan como referencia): `core-web-vitals` y `performance` de `addyosmani/web-quality-skills`
(commit `afa8da9`) y `web-perf` de `cloudflare/skills` (commit `1a33048`).

| Criterio de las skills | Aplicación aquí |
| --- | --- |
| Medir antes de optimizar; no comparar laboratorio con campo; TBT no es INP | Línea base de 5 ejecuciones; sin CrUX (sección 2); INP «sin datos». |
| LCP: recurso descubrible en el HTML y priorizado con `fetchpriority="high"`; preload solo si el trace muestra descubrimiento tardío | W1 (la imagen ya es descubrible; falta la prioridad) y W2/B3 (preloads que compiten). |
| Preconnect a los orígenes necesarios (≤ 4) | B1 (un único origen: la API). |
| CLS: reservar el espacio del contenido dinámico | B2. |
| Imágenes: tamaño correcto y formatos modernos (AVIF/WebP) | W2, B3 y W3 (hipótesis, se mide). |
| «Cuantificar el impacto; no priorizar cambios con 0 ms»; «skip non-issues» | W5 y B6 se documentan sin tocar; CSS bloqueante con 0 ms en el audit clásico. |
| Speculation Rules, View Transitions, service workers, Early Hints | Descartados: sin problema medido que resuelvan (el website es de una sola página; Early Hints depende del proxy). |
| Virtualizar listas de más de 100 elementos | B7: 95 filas y TBT 0 ms; no se aplica sin evidencia. |

## 8. Matriz de correcciones (priorizada)

Orden por impacto esperado y riesgo. Cada fila es un commit independiente con su medición.

| # | Problema | Aplicación | Prioridad | Corrección | Verificación |
| --- | --- | --- | --- | --- | --- |
| 1 | W1 | Corporate | Alta | `fetchPriority="high"` + `preload` en la imagen del hero | LCP móvil; `lcp-discovery-insight` |
| 2 | W2 | Corporate | Media | `sizes` y carga sin preload del logo | Peso; petición del logo; LCP móvil |
| 3 | W3 | Corporate | Baja | AVIF en `images.formats` | Bytes de la imagen LCP; `image-delivery-insight` |
| 4 | W4 | Corporate | Media | Contraste de los números del proceso | Accessibility; `color-contrast` |
| 5 | B2 | Backoffice | Alta | Estructura reservada en el resumen del gestor | CLS de `/gestor-incidencias` |
| 6 | B1 | Backoffice | Alta | `preconnect` al origen de la API | LCP móvil del dashboard; `uses-rel-preconnect` |
| 7 | B3 | Backoffice | Media | `sizes` en los logos, sin preload en el sidebar | Peso; petición del logo |
| 8 | B4 | Backoffice | Media | `text-slate-600` en las etiquetas del dashboard | Accessibility; `color-contrast` |
| 9 | D1 | Backoffice | Mantenimiento | Hook `useApiRequest` en las seis vistas | Lint, typecheck, Jest, build; pruebas en navegador de carga, filtros, error y reintento |
| 10 | D2 | Backoffice | Mantenimiento | Componente `LoadErrorAlert` en las cinco vistas | Ídem; aviso de error con la API parada |

## 9. Riesgos y limitaciones

- **Laboratorio en `localhost`:** sin latencia real ni CDN; TTFB no representativo. El throttling simulado (Lantern)
  estima LCP a partir de la cascada observada: cambios de prioridad pueden mover más el valor simulado que el real.
- **Sin datos de campo:** ni CrUX ni RUM; ninguna mejora de este documento es una mejora de campo demostrada.
- **INP no medible** en modo navegación; TBT solo como indicio.
- **Backoffice con sesión inyectada:** el token se guarda antes de cargar la app; refleja una visita con sesión ya
  iniciada (el caso habitual), no el paso por `/login`.
- **Datos:** el gestor se mide con las 95 incidencias de la copia de la base; con otro volumen cambian los valores.
