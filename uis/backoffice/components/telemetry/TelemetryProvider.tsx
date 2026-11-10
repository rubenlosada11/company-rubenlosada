"use client";

import { usePathname } from "next/navigation";
import { useReportWebVitals } from "next/web-vitals";
import { useEffect } from "react";
import { track } from "@/lib/telemetry";
import { captureFrontendError } from "@/lib/telemetryCapture";
import { APP_VERSION, type FrontendEventProperties, type Section } from "@/lib/telemetryCatalog";
import { sectionFor } from "@/lib/telemetrySections";

/**
 * Telemetría transversal del backoffice, montada una sola vez en `app/layout.tsx`. No pinta nada.
 *
 * - `navigation_section_viewed`: en la carga y en cada cambio de ruta (`usePathname`). Solo la sección del catálogo,
 *   nunca la URL ni sus parámetros. La misma sección en menos de 2 s no se repite (doble montaje de Strict Mode,
 *   redirecciones como `/inventory` → `/inventory/products`).
 * - `frontend_error_captured`: `window.onerror` y `unhandledrejection` (los límites de error de Next.js informan de lo
 *   suyo en `app/**\/error.tsx`).
 * - `page_performance_measured`: Web Vitals de la carga de la página (`useReportWebVitals` de Next.js, sin dependencias
 *   nuevas). Un evento por carga, al ocultarse la página por primera vez, cuando CLS e INP ya son definitivos.
 */
export function TelemetryProvider() {
  const pathname = usePathname();

  // Antes que el resto de efectos: así los listeners de Web Vitals quedan registrados antes que el que emite el evento.
  useReportWebVitals(collectWebVital);

  useEffect(() => {
    const onPopState = () => {
      lastPopState = Date.now();
    };
    const onError = (event: ErrorEvent) => {
      // Sin objeto de error (p. ej. «Script error.» de otro origen) no hay nada que clasificar sin el mensaje.
      if (event.error) void captureFrontendError(event.error, "none", "uncaught_exception");
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      void captureFrontendError(event.reason, "none", "unhandled_rejection");
    };
    const onHidden = () => {
      if (document.visibilityState === "hidden") reportWebVitals();
    };
    // Web Vitals al ocultar la página: en `window` (fase de burbuja), después de los listeners de `document`, donde
    // `web-vitals` cierra CLS e INP (y registra el suyo tarde, tras el FCP). Este efecto se registra antes que el
    // listener de envío del servicio (que nace con el primer `track`, en el efecto de navegación de abajo): así el
    // evento ya está en la cola cuando sale el beacon.
    window.addEventListener("visibilitychange", onHidden);
    window.addEventListener("popstate", onPopState);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);

    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
      window.removeEventListener("visibilitychange", onHidden);
    };
  }, []);

  useEffect(() => {
    reportNavigation(pathname);
  }, [pathname]);

  return null;
}

// --- Navegación -------------------------------------------------------------------------------------------------

const SAME_SECTION_MS = 2_000;
/** Ventana en la que un cambio de ruta se atribuye a los botones atrás/adelante del navegador. */
const POPSTATE_MS = 1_000;

let lastSection: Section | null = null;
let lastSectionAt = 0;
let lastPopState = 0;

function reportNavigation(pathname: string): void {
  const section = sectionFor(pathname);
  const now = Date.now();
  if (section === lastSection && now - lastSectionAt < SAME_SECTION_MS) return;
  const trigger: FrontendEventProperties["navigation_section_viewed"]["navigation_trigger"] =
    lastSection === null ? "initial_load" : now - lastPopState < POPSTATE_MS ? "browser_history" : "in_app_navigation";
  track("navigation_section_viewed", { section, previous_section: lastSection, navigation_trigger: trigger });
  lastSection = section;
  lastSectionAt = now;
}

// --- Web Vitals -------------------------------------------------------------------------------------------------

type Perf = FrontendEventProperties["page_performance_measured"];

interface WebVital {
  name: string;
  value: number;
  navigationType?: string;
}

const MAX_DURATION_MS = 3_600_000;

const vitals: { lcp: number | null; cls: number | null; inp: number | null; ttfb: number | null; type: string | null } =
  { lcp: null, cls: null, inp: null, ttfb: null, type: null };
let vitalsSection: Section | null = null;
let vitalsReported = false;

const duration = (value: number) => Math.min(Math.max(Math.round(value * 100) / 100, 0), MAX_DURATION_MS);

/** Referencia estable (lo pide `useReportWebVitals`): guarda el último valor de cada métrica de esta carga. */
function collectWebVital(metric: WebVital): void {
  vitalsSection ??= sectionFor(window.location.pathname);
  vitals.type ??= metric.navigationType ?? null;
  if (metric.name === "LCP") vitals.lcp = duration(metric.value);
  else if (metric.name === "INP") vitals.inp = duration(metric.value);
  else if (metric.name === "TTFB") vitals.ttfb = duration(metric.value);
  else if (metric.name === "CLS") vitals.cls = Math.min(Math.round(metric.value * 10_000) / 10_000, 10);
  // FCP y FID no están en la allowlist de `page_performance_measured`: no se envían.
}

function navigationType(type: string | null): Perf["navigation_type"] {
  if (type === "reload") return "reload";
  if (type === "back-forward" || type === "back_forward" || type === "back-forward-cache") return "back_forward";
  return "navigate";
}

function deviceClass(): Perf["device_class"] {
  const width = window.innerWidth;
  if (width < 768) return "mobile";
  if (width < 1024) return "tablet";
  return "desktop";
}

function reportWebVitals(): void {
  if (vitalsReported || vitalsSection === null) return;
  if (vitals.lcp === null && vitals.cls === null && vitals.inp === null && vitals.ttfb === null) return;
  vitalsReported = true;
  track("page_performance_measured", {
    section: vitalsSection,
    lcp_ms: vitals.lcp,
    cls: vitals.cls,
    inp_ms: vitals.inp,
    ttfb_ms: vitals.ttfb,
    navigation_type: navigationType(vitals.type),
    device_class: deviceClass(),
    app_version: APP_VERSION,
  });
}
