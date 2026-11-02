# REPORT.md — Resultados de la auditoría de rendimiento

Resultados de la auditoría de rendimiento de `uis/website` (corporate) y `uis/backoffice` (rama
`feature/frontend-performance-audit`, 2026-11-02). Diagnóstico inicial, metodología y causas raíz:
[`AUDIT.md`](./AUDIT.md). Evidencias: [`audit/before/`](./audit/before/) y [`audit/after/`](./audit/after/)
(informe HTML, JSON y captura PNG de la ejecución mediana de cada página y dispositivo; `runs.json` con las cinco
ejecuciones). Todas las cifras son de laboratorio (Lighthouse 12.8.2, throttling simulado, `localhost`).

## 1. Resumen ejecutivo

- **Objetivo cumplido en ambos frontends:** al menos una puntuación de Lighthouse mejora en cada uno y ninguna empeora.
  - **Corporate:** accesibilidad **96 → 100** (escritorio y móvil) y rendimiento móvil **96 → 97**, con LCP móvil
    2639 → 2591 ms, TBT 106 → 59 ms, Speed Index 865 → 766 ms y −22 KiB de peso. Escritorio ya estaba en 100.
  - **Backoffice:** `/gestor-incidencias` pasa de rendimiento **95 → 99** al eliminar su único problema de Core Web
    Vitals (CLS **0,133 → 0**); accesibilidad del dashboard **96 → 100** en escritorio y móvil.
- **Siete correcciones conservadas** (W2, W3, W4, B1, B2, B3, B4), una por commit y medida por separado, y **una
  descartada** (W1, `fetchpriority` en el hero) porque empeoraba la simulación y no mejoraba con throttling real.
- **Dos refactorizaciones integradas** en el backoffice: el hook `useApiRequest` (6 copias del mismo patrón de
  petición) y el componente `LoadErrorAlert` (5 copias del aviso de error), sin cambiar comportamiento ni métricas.
- **Pendiente principal:** el LCP móvil del dashboard (~3,05 s) depende del modelo de sesión (el panel se pinta tras
  validar el token con la API); mejorarlo exige un cambio de arquitectura que queda fuera de esta auditoría.

## 2. Comparativa de puntuaciones antes / después

Mediana de 5 ejecuciones por página y dispositivo, mismas URLs, dispositivos, versión y configuración de Lighthouse
que la línea base.

| Aplicación | Página | Dispositivo | Performance | Accessibility | Best Practices | SEO |
| --- | --- | --- | --- | --- | --- | --- |
| Corporate | Home | Escritorio | 100 → 100 (=) | 96 → **100 (+4)** | 100 → 100 (=) | 100 → 100 (=) |
| Corporate | Home | Móvil | 96 → **97 (+1)** | 96 → **100 (+4)** | 100 → 100 (=) | 100 → 100 (=) |
| Backoffice | Dashboard | Escritorio | 100 → 100 (=) | 96 → **100 (+4)** | 100 → 100 (=) | 63 → 63 (=, `noindex`) |
| Backoffice | Dashboard | Móvil | 93 → 93 (=) | 96 → **100 (+4)** | 100 → 100 (=) | 63 → 63 (=, `noindex`) |
| Backoffice | Gestor de incidencias | Escritorio | 95 → **99 (+4)** | 100 → 100 (=) | 100 → 100 (=) | 63 → 63 (=, `noindex`) |

Ejecuciones individuales de rendimiento (antes → después): website móvil 96·96·96·96·96 → 97·97·97·97·97; dashboard
móvil 92·94·93·85·93 → 93·94·93·94·92; gestor 95·95·95·95·95 → 99·99·99·99·99. Capturas:
`audit/{before,after}/<app>/<página>-<dispositivo>.png`.

## 3. Evolución de las métricas

Métricas de laboratorio (mediana de 5). **INP: sin datos** (no existe en modo navegación ni hay CrUX); TBT es solo
su indicador de laboratorio. TTFB es de `localhost`.

| Aplicación | Página | Dispositivo | LCP | CLS | TBT | FCP | Speed Index | TTFB | Peso | Peticiones |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Corporate | Home | Escritorio | 561 → 564 ms (+3) | 0 → 0 | 2 → 0 ms | 220 → 219 ms | 330 → 300 ms (−30) | 6 → 7 ms | 266 → 246 KiB (−20) | 12 → 12 |
| Corporate | Home | Móvil | **2639 → 2591 ms (−47)** | 0 → 0 | **106 → 59 ms (−47)** | 767 → 766 ms | **865 → 766 ms (−99)** | 6 → 6 ms | **273 → 251 KiB (−22)** | 12 → 12 |
| Backoffice | Dashboard | Escritorio | 768 → 751 ms (−17) | 0 → 0 | 2 → 0 ms | 218 → 218 ms | 316 → 282 ms (−34) | 5 → 5 ms | 314 → 313 KiB | 44 → 44 |
| Backoffice | Dashboard | Móvil | 3056 → 3054 ms (−2) | 0 → 0 | 133 → 109 ms (−24) | 765 → 764 ms | 765 → 764 ms | 5 → 4 ms | 266 → 262 KiB (−4) | 26 → 26 |
| Backoffice | Gestor | Escritorio | 842 → 850 ms (+8) | **0,133 → 0** | 0 → 0 ms | 214 → 215 ms | 336 → 371 ms (+35) | 4 → 4 ms | 342 → 341 KiB | 48 → 48 |

Lectura: las variaciones de menos de ~20 ms de LCP en escritorio, de ±25 ms de TBT en el dashboard móvil (una
ejecución de la línea base dio 380 ms) y el Speed Index del gestor (rangos 297–411 ms antes y 272–373 ms después)
están dentro del ruido entre ejecuciones. Lo que se repite en las cinco ejecuciones es: CLS del gestor a 0, TBT del
website móvil (todas las ejecuciones de después por debajo de todas las de antes), su LCP y los bytes.

### Core Web Vitals (laboratorio)

| Página | LCP | CLS | INP |
| --- | --- | --- | --- |
| Corporate móvil | 2,64 s → 2,59 s (sigue «mejorable», a 0,09 s de «bueno») | 0 | sin datos |
| Dashboard móvil | 3,06 s → 3,05 s («mejorable») | 0 | sin datos |
| Gestor escritorio | 0,84 s → 0,85 s («bueno») | **0,133 → 0 («mejorable» → «bueno»)** | sin datos |
| Resto | < 0,8 s («bueno») | 0 | sin datos |

## 4. Problemas corregidos y cambios por aplicación

Cada corrección es un commit independiente y se midió sola, sobre la anterior, en la misma URL y dispositivo (5
ejecuciones salvo las de accesibilidad, con 3; los valores son medianas).

### Sitio corporativo (`uis/website`)

| ID | Cambio | Ficheros | Medición (antes → después) | Commit |
| --- | --- | --- | --- | --- |
| W2 | Logo de la cabecera con `sizes="180px"`, carga `eager` y **sin** precarga | `components/SiteHeader.tsx` | Móvil: rendimiento 96 → 97, LCP 2639 → 2584 ms, TBT 106 → 56 ms; logo de 3840 px / 9,4 KB a 384 px / 6,6 KB. Escritorio: 100 → 100 | `2789cf9` |
| W3 | Imágenes en AVIF (`images.formats`) | `next.config.ts` | Peso móvil 271 → 251 KiB (hero 39,8 → 22,2 KB); `image-delivery-insight` 29 → 16 KiB; rendimiento 97 → 97 y LCP 2584 → 2596 ms (ruido) | `7702b58` |
| W4 | Números del proceso de `blue-200` a `blue-500` (1,41 → 3,73:1) | `components/Process.tsx` | Accesibilidad 96 → 100 (escritorio y móvil) | `56a85e7` |
| W1 | `fetchPriority="high"` en la imagen del hero | `components/Hero.tsx` | **Descartada** (ver sección 7) | — |

### Backoffice (`uis/backoffice`)

| ID | Cambio | Ficheros | Medición (antes → después) | Commit |
| --- | --- | --- | --- | --- |
| B2 | El resumen del gestor reserva su alto durante la primera carga | `components/gestor-incidencias/IncidentSummary.tsx` | `/gestor-incidencias`: CLS 0,133 → 0, rendimiento 95 → 99. En navegador, el listado queda en la misma posición (908 px) antes y después de llegar el resumen | `8c545a0` |
| B1 | `preconnect` con `crossorigin` al origen de la API | `app/layout.tsx` | `uses-rel-preconnect` suspenso (150 ms) → aprobado; `/auth/me` sale antes (LCP observado de la ejecución mediana 398 → 358 ms). LCP simulado móvil 3056 → 3055 ms; rendimiento 93 → 94 (dentro del ruido) | `6aac2d7` |
| B3 | `sizes` en los cinco logos; el del sidebar sin precarga | `components/Sidebar.tsx`, `Topbar.tsx`, `auth/AuthGate.tsx`, `auth/AuthShell.tsx` | Logo de 1200/3840 px (9,4 KB) a 256 px (5,1 KB); LCP escritorio 768 → 750 ms; puntuaciones iguales | `546be6d` |
| B4 | Etiquetas del dashboard sobre `bg-slate-100` a `text-slate-600` (4,34 → ≥ 4,5:1) | `components/Overview.tsx`, `Explorer.tsx` | Accesibilidad 96 → 100 (escritorio y móvil) | `72b50f6` |
| R1 | Hook `useApiRequest` (ver sección 6) | `lib/useApiRequest.ts` + 6 componentes | Sin cambio de métricas (gestor 99, CLS 0) | `48156e9` |
| R2 | Componente `LoadErrorAlert` (ver sección 6) | `components/LoadErrorAlert.tsx` + 5 componentes | Sin cambio de métricas | `929a5b9` |

## 5. Skills utilizadas y recomendaciones aplicadas

Se consultaron (sin instalarlas) `core-web-vitals` y `performance` de `addyosmani/web-quality-skills` y `web-perf` de
`cloudflare/skills` (detalle en `AUDIT.md` §7).

| Recomendación de las skills | Resultado |
| --- | --- |
| Medir antes de optimizar, con condiciones fijas y varias ejecuciones; no tratar TBT como INP ni el laboratorio como campo | Aplicada en todo el proceso |
| «Verify before recommending» / «Quantify impact» | W1 se midió con dos métodos y se descartó al no mejorar; B1 se mantiene y se informa que no mueve el LCP simulado |
| LCP: imagen descubrible y con `fetchpriority="high"` | Probada (W1) y **descartada** por las mediciones |
| Preload solo cuando el recurso se descubre tarde | Aplicada: fuera los preloads de logos que no son LCP (W2, B3) |
| Preconnect a los orígenes necesarios | Aplicada (B1) |
| CLS: reservar el espacio del contenido dinámico | Aplicada (B2) |
| Tamaño correcto y formatos modernos de imagen | Aplicada (W2, W3, B3) |
| Speculation Rules, View Transitions, Early Hints, virtualización, inline de CSS crítico | No aplicadas: sin problema medido que resuelvan o fuera de la arquitectura actual (`AUDIT.md` §7) |

## 6. Refactorizaciones realizadas

| | R1 — `useApiRequest` | R2 — `LoadErrorAlert` |
| --- | --- | --- |
| Duplicidad (`AUDIT.md` §6) | D1: petición con clave, `AbortController` y estados de carga/error copiada en 6 sitios | D2: aviso rojo con «Reintentar» copiado en 5 sitios |
| Abstracción | `lib/useApiRequest.ts`: `useApiRequest<T>(key, request, errorMessage, { keepDataOnError, onSuccess })` → `{ data, error, loading, settled, reload, update }`. Usa `useEffectEvent` (React 19.2) para que las funciones nuevas en cada render no repitan la petición | `components/LoadErrorAlert.tsx`: `title`, `message`, `onRetry` y aclaraciones opcionales |
| Integrada en | `IncidentList`, `IncidentSummary`, `SupplierDirectory`, `MovementHistory`, `useProducts` (`formParts.tsx`); `ProductList` deja de reimplementar `useProducts` y lo usa | `IncidentList`, `IncidentSummary`, `SupplierDirectory`, `MovementHistory`, `ProductList` |
| Contratos | Sin cambios: mismas llamadas a la API, mismos textos, mismos estados (los listados conservan los datos mientras recargan; productos los conserva también si falla) | Mismos textos; el botón de proveedores pasa a 44 px, como los demás |
| Tamaño | 6 componentes: −206 / +79 líneas, más el hook (89 líneas) | 5 componentes: −60 / +20 líneas, más el componente (28 líneas) |
| Verificación | Lint, typecheck, Jest 148/148, build y 17 comprobaciones en navegador en escritorio y móvil (carga, filtros, cambio de estado optimista, errores simulados con la red cortada y «Reintentar») | Ídem |

`useProductStock` no se migró: su estado («sin producto elegido», «cargando», «listo», «error» por SKU) no es el de un
listado, y forzarlo en el hook lo complicaría sin ganar nada.

## 7. Impacto de cada corrección y cambios con mayor impacto

| Corrección | Impacto medido | Valoración |
| --- | --- | --- |
| **B2** — alto reservado en el resumen del gestor | CLS 0,133 → 0 y rendimiento 95 → 99 en las 5 ejecuciones | **Mayor impacto**: único Core Web Vital que pasa de «mejorable» a «bueno» |
| **W4 / B4** — contraste | Accesibilidad 96 → 100 en las cuatro combinaciones afectadas | Alto (puntuación), coste mínimo |
| **W2** — logo del website sin preload y a su tamaño | Móvil 96 → 97; TBT 106 → 56 ms y LCP 2639 → 2584 ms en las 5 ejecuciones | Medio: es la mejora de rendimiento del website |
| **W3** — AVIF | −20 KiB por visita (−7 %), la imagen LCP pesa un 45 % menos; LCP y puntuación sin cambio | Bajo en Lighthouse, real en datos móviles |
| **B3** — logos del backoffice | −4 KB por visita; LCP de escritorio −17 ms | Bajo |
| **B1** — preconnect a la API | Aviso `uses-rel-preconnect` resuelto; `/auth/me` antes en la traza; LCP simulado sin cambio | Bajo en laboratorio; puede valer más con latencia real (API en otro dominio) |
| **R1 / R2** — refactorizaciones | Sin cambio de métricas (no era su objetivo) | Mantenimiento: los 6 componentes afectados pierden 266 líneas y ganan 99 (más 117 del hook y el componente nuevos) |
| W1 — `fetchpriority` en el hero | Simulado: LCP móvil +100 ms (96 → 95); DevTools: 2149 → 2152 ms | **Descartada** |

Cambios con mayor impacto: **B2** (CLS del gestor), **W4 + B4** (accesibilidad a 100 en todas las páginas) y **W2**
(rendimiento del website móvil).

## 8. Problemas no resueltos y justificación

| Problema | Por qué no se resuelve aquí | Siguiente paso posible |
| --- | --- | --- |
| LCP móvil del dashboard (~3,05 s, «mejorable») | El panel solo se pinta tras hidratar y validar la sesión con `GET /auth/me` (token en `localStorage`, decisión de AUTH-02). El preconnect (B1) acorta la conexión, pero el LCP simulado lo domina el trabajo de CPU de hidratar el panel. Resolverlo exige cambiar el modelo de sesión. | Cookie de sesión + comprobación en el servidor (middleware) para enviar el panel en el HTML. Requiere confirmación (arquitectura). |
| LCP móvil del website (~2,6 s, «mejorable» por 0,1 s) | Con throttling real el LCP coincide con el primer pintado (HTML + CSS + fuentes); la prioridad de la imagen no es el cuello de botella. Lo que queda es el CSS bloqueante (7 KiB, 70 ms estimados) y el runtime de React. | Probar `experimental.inlineCss` de Next cuando deje de ser experimental, o medir en producción (Cloudflare, HTTP/2), donde la latencia por petición es otra. |
| JS sin usar (54 KiB website, 26 KiB backoffice) | Es el runtime de React/Next App Router. | — |
| SEO 63 del backoffice | `noindex` intencionado. | — |
| INP | No medible en laboratorio en modo navegación. | Medir en campo (RUM con `web-vitals`) si se publica el backoffice. |
| Preconnect en `/login` | En rutas dinámicas Next solo manda la pista en el payload RSC, no en el `<head>`. | Aceptado: el login no está en la ruta crítica medida. |

## 9. Regresiones detectadas y resolución

| Caso | Detección | Resolución |
| --- | --- | --- |
| W1 (`fetchPriority="high"` en el hero) empeoraba el LCP móvil simulado: 2639 → 2736 ms (rendimiento 96 → 95) | Medición de la corrección (3 ejecuciones), consistente en todas | Se investigó: en la traza observada la imagen pasa de prioridad *Low* a *High* y el LCP observado sin throttling baja (368 → 306 ms), pero en la simulación de Lighthouse la imagen compite por el ancho de banda con fuentes y JS. A/B con throttling **real** de DevTools (5 + 5 ejecuciones): LCP 2149 ms sin W1 y 2152 ms con W1, sin diferencia. Probada otra vez encima de W2 (sin el preload del logo compitiendo): 2584 → 2749 ms. **Se revirtió** y no se commiteó. |
| Speed Index del gestor 336 → 371 ms | Comparativa final | Dentro del ruido (rangos solapados, ver sección 3), aunque es plausible un efecto pequeño de B2: el hueco reservado queda en blanco hasta que llega el resumen, en lugar de mostrar antes el listado. Se acepta: elimina un CLS de 0,133 y el Speed Index sigue muy por debajo del umbral (1,3 s en escritorio). |
| Ninguna otra en las correcciones conservadas | Comparativa de la sección 2 y pruebas en navegador | — |

Pruebas funcionales finales (Fase 8), con los builds de producción: website 12/12 en escritorio y móvil (secciones,
imágenes AVIF cargadas, CTA, anclas, menú móvil, consola limpia); backoffice 17/17 en escritorio y 17/17 en móvil
(gestor: carga, filtros, cambio de estado optimista, errores del listado y del resumen con «Reintentar»; proveedores:
filtro y error; inventario: productos, fallo al actualizar sin vaciar la tabla, error en la primera carga, historial,
filtro por almacén y selector del formulario de entrada; dashboard y filtros de iniciativas; consola sin errores
inesperados). Lint y typecheck en ambas apps, Jest del backoffice 148/148 y `next build` en verde.

## 10. Limitaciones de las mediciones

- **Laboratorio en `localhost`:** sin red real ni CDN; TTFB de 4–6 ms no representativo. El throttling simulado
  (Lantern) modela mal los cambios de prioridad (caso W1): por eso W1 se contrastó con throttling real.
- **Sin datos de campo:** ni CrUX (cuota anónima de PSI agotada y sitios con poco tráfico) ni RUM. Ninguna mejora de
  este informe es una mejora de campo demostrada; INP sin datos.
- **Ruido:** diferencias de ±1 punto de rendimiento, ±20 ms de LCP en escritorio o ±50 ms de TBT en móvil entran en la
  variación entre ejecuciones (ver `runs.json`). Solo se atribuyen mejoras que se repiten en las cinco ejecuciones.
- **Datos del gestor:** las pruebas en navegador (repetidas varias veces) pasaron 8 incidencias de «abierta» a «en
  curso» en la **copia** de la base: mismo número de filas (95) y misma estructura del resumen, así que la medición
  AFTER es comparable.
- **Backoffice con sesión inyectada** antes de cargar la app (visita con sesión ya iniciada), no el paso por `/login`.

## 11. Conclusiones

1. Los dos frontends ya partían de un buen nivel (rendimiento 93–100): no había grandes regresiones que atacar, sino
   problemas concretos. Los que tenían evidencia se corrigieron: un CLS real en el gestor, contraste insuficiente en
   ambas apps y recursos de imagen mal dimensionados o precargados sin motivo.
2. La auditoría demuestra el valor de medir cada cambio: la optimización «de manual» (`fetchpriority` en la imagen
   LCP) empeoraba la puntuación aquí y se descartó con dos métodos de medición distintos.
3. El límite del backoffice no es de código sino de arquitectura: mientras la sesión se valide en el cliente, el
   panel no puede pintarse antes de hidratar y llamar a la API. Es la recomendación principal para un siguiente
   paso, que requiere decisión del equipo.
4. Las refactorizaciones dejan un único punto para las peticiones de los listados y para sus avisos de error, lo que
   facilita aplicar mejoras futuras (p. ej. caché o paginación) en un solo sitio.
5. Ninguna de estas mejoras está validada con usuarios reales: si se publican, conviene medir en campo (RUM con
   `web-vitals`) antes de atribuirles impacto en producción.
