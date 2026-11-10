/**
 * Captura transversal de la telemetría técnica del backoffice: errores de JavaScript y fallos de comunicación con la
 * API. Construye las propiedades del contrato (sin mensajes, trazas, URLs ni valores) y llama a `track()`, la única
 * función de envío. Control de frecuencia del plan (§13.4):
 *
 * - `frontend_error_captured`: el primer error de cada `fingerprint` se envía al momento; los repetidos durante 60 s se
 *   agrupan en un evento con `occurrence_count`. Máximo 20 eventos de error por minuto; el exceso se cuenta en
 *   `telemetry_events_dropped` (`rate_limited`). Un mismo objeto de error capturado por dos vías (límite de error y
 *   `window.onerror`) cuenta una sola vez.
 * - `backend_request_failed`: uno cada 30 s por (`api_route`, `failure_kind`, método), con `occurrence_count`.
 */
import { track } from "@/lib/telemetry";
import { APP_VERSION, type FrontendEventProperties, type HttpMethod } from "@/lib/telemetryCatalog";
import { apiRouteTemplate, sectionFor } from "@/lib/telemetrySections";

type ErrorProps = FrontendEventProperties["frontend_error_captured"];
type RequestProps = FrontendEventProperties["backend_request_failed"];
export type ErrorBoundaryName = ErrorProps["boundary"];
export type RequestFailureKind = RequestProps["failure_kind"];

export const ERROR_WINDOW_MS = 60_000;
export const MAX_ERRORS_PER_MINUTE = 20;
export const REQUEST_FAILURE_WINDOW_MS = 30_000;

const ERROR_NAME = /^[A-Za-z_][A-Za-z0-9_.]{0,79}$/;
const DIGEST = /^[A-Za-z0-9]{1,64}$/;
const HTTP_METHODS: readonly HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

function currentSection() {
  return sectionFor(typeof window === "undefined" ? "/" : window.location?.pathname);
}

// --- Agregación por ventana (común a errores y fallos de red) ---------------------------------------------------

interface Window_ {
  repeats: number;
  timer: ReturnType<typeof setTimeout>;
}

/**
 * Primer caso al momento; los repetidos de la misma clave dentro de la ventana se envían juntos al cerrarla
 * (`occurrence_count`). Así nunca se pierde la primera señal (§13.2) y un bucle de errores no inunda la cola.
 */
function aggregator(windowMs: number, emit: (key: string, occurrences: number) => void) {
  const open = new Map<string, Window_>();
  return (key: string) => {
    const current = open.get(key);
    if (current) {
      current.repeats += 1;
      return;
    }
    emit(key, 1);
    const entry: Window_ = {
      repeats: 0,
      timer: setTimeout(() => {
        open.delete(key);
        if (entry.repeats > 0) emit(key, entry.repeats);
      }, windowMs),
    };
    open.set(key, entry);
  };
}

// --- Errores de JavaScript --------------------------------------------------------------------------------------

const errorProps = new Map<string, Omit<ErrorProps, "occurrence_count">>();
const captured = new WeakSet<object>();
let minuteStart = 0;
let errorsThisMinute = 0;

const emitError = aggregator(ERROR_WINDOW_MS, (fingerprint, occurrences) => {
  const props = errorProps.get(fingerprint);
  if (!props) return;
  const now = Date.now();
  if (now - minuteStart >= 60_000) {
    minuteStart = now;
    errorsThisMinute = 0;
  }
  if (errorsThisMinute >= MAX_ERRORS_PER_MINUTE) {
    track("telemetry_events_dropped", {
      component: "frontend_emitter",
      drop_reason: "rate_limited",
      affected_event_type: "frontend_error_captured",
      dropped_count: 1,
      window_seconds: 60,
    });
    return;
  }
  errorsThisMinute += 1;
  track("frontend_error_captured", { ...props, occurrence_count: occurrences });
});

/** Nombre de la clase del error (nunca el mensaje). */
export function errorName(error: unknown): string {
  const name =
    error instanceof Error
      ? error.name
      : ((error as { constructor?: { name?: unknown } } | null)?.constructor?.name ?? typeof error);
  return typeof name === "string" && ERROR_NAME.test(name) ? name : "Error";
}

/**
 * Primer marco de la traza que es código propio (servido desde este origen), sin origen, query ni fragmento:
 * `/_next/static/chunks/app/page-abc.js:1:2345`. Sin traza, cadena vacía.
 */
export function firstOwnFrame(stack: string | undefined, origin: string): string {
  if (!stack) return "";
  for (const line of stack.split("\n")) {
    const match = line.match(/(https?:\/\/[^\s)]+|webpack-internal:\/\/\/[^\s)]+)/);
    if (!match) continue;
    const url = match[1];
    if (url.startsWith("http") && !url.startsWith(origin)) continue;
    return url
      .replace(origin, "")
      .replace(/[?#][^:]*/, "")
      .replace(/^webpack-internal:\/\/\//, "");
  }
  return "";
}

async function sha256Hex16(text: string): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest).slice(0, 8), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function errorKind(error: unknown, fallback: ErrorProps["error_kind"]): ErrorProps["error_kind"] {
  const name = errorName(error);
  // Se mira el mensaje solo para clasificar; nunca se envía.
  const message = error instanceof Error ? error.message : "";
  if (name === "ChunkLoadError" || /Loading (CSS )?chunk [\w-]+ failed|Failed to fetch dynamically imported module/i.test(message)) {
    return "chunk_load_error";
  }
  return fallback;
}

/**
 * `frontend_error_captured` para un error de los límites de error de Next.js o de `window`. No lanza nunca. La huella
 * (SHA-256) es asíncrona: la promesa devuelta termina cuando el evento ya está capturado (la usan los tests).
 */
export function captureFrontendError(
  error: unknown,
  boundary: ErrorBoundaryName,
  kind: ErrorProps["error_kind"]
): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (error && typeof error === "object") {
    if (captured.has(error)) return Promise.resolve();
    captured.add(error);
  }
  const name = errorName(error);
  const origin = window.location?.origin ?? "";
  const frame = firstOwnFrame(error instanceof Error ? error.stack : undefined, origin);
  const rawDigest = (error as { digest?: unknown } | null)?.digest;
  const props: Omit<ErrorProps, "occurrence_count" | "fingerprint"> = {
    error_kind: errorKind(error, kind),
    error_name: name,
    boundary,
    section: currentSection(),
    digest: typeof rawDigest === "string" && DIGEST.test(rawDigest) ? rawDigest : null,
    app_version: APP_VERSION,
  };
  return sha256Hex16(`${name}|${frame}`)
    .then((fingerprint) => {
      if (!fingerprint) return;
      errorProps.set(fingerprint, { ...props, fingerprint });
      emitError(fingerprint);
    })
    .catch(() => undefined);
}

// --- Fallos de comunicación con la API --------------------------------------------------------------------------

const requestProps = new Map<string, Omit<RequestProps, "occurrence_count">>();

const emitRequestFailure = aggregator(REQUEST_FAILURE_WINDOW_MS, (key, occurrences) => {
  const props = requestProps.get(key);
  if (props) track("backend_request_failed", { ...props, occurrence_count: occurrences });
});

/**
 * `backend_request_failed`: la llamada no ha obtenido una respuesta útil (sin conexión, tiempo agotado, API sin
 * configurar, respuesta ilegible o con forma inesperada). Los 4xx/5xx con respuesta no cuentan: los ve el backend.
 */
export function reportRequestFailure(kind: RequestFailureKind, path: string, method: string | undefined): void {
  if (typeof window === "undefined") return;
  const httpMethod = (method ?? "GET").toUpperCase() as HttpMethod;
  const props: Omit<RequestProps, "occurrence_count"> = {
    failure_kind: kind,
    api_route: apiRouteTemplate(path),
    http_method: HTTP_METHODS.includes(httpMethod) ? httpMethod : "GET",
    section: currentSection(),
  };
  const key = `${props.http_method} ${props.api_route} ${kind}`;
  requestProps.set(key, props);
  emitRequestFailure(key);
}
