/**
 * `TelemetryService`: único punto de captura y envío de telemetría del backoffice (fase de captura del plan,
 * `docs/telemetry/telemetry-capture.md`).
 *
 * API pública: **`track(eventType, properties)`**. Componentes y hooks nunca hacen peticiones de telemetría: llaman a
 * `track` y el servicio se encarga del resto.
 *
 * - **Envelope automático** (§8 del plan): `eventId` (UUID v4), `timestamp` (ISO 8601 UTC del momento de captura),
 *   `sessionId` (sesión autenticada, ver `lib/telemetrySession.ts`), `userId` (siempre `null`: lo pone el receptor a
 *   partir del token, el navegador nunca lo calcula), `event_type`, `schemaVersion` (del catálogo), `requestId` (solo en
 *   `form_submitted`), `source = "frontend"`, `environment` y `properties`.
 * - **Allowlist**: solo eventos del catálogo con `source` `frontend` (`lib/telemetryCatalog.ts`) y exactamente sus
 *   propiedades. Un evento que no cumple se descarta (y se cuenta en `telemetry_events_dropped`).
 * - **Lotes**: cola en memoria; se envía un lote `{ events: [...] }` cuando pasan 10 s desde el primer evento pendiente
 *   o cuando la cola llega a 20, lo que ocurra antes. Nunca una petición por evento.
 * - **Reintentos**: un solo lote en vuelo; si falla (red, 408, 429, 5xx) se reintenta hasta 3 veces con backoff
 *   exponencial (1 s, 2 s, 4 s) sin bloquear la interfaz ni las capturas nuevas, que esperan en la cola. Agotados los
 *   intentos (o ante un 4xx, que no se arregla repitiendo) el lote se descarta y se cuenta.
 * - **Al ocultar la página** (`visibilitychange` → `hidden`, y `pagehide`): los eventos pendientes, y el lote que
 *   esperaba un reintento, salen con `navigator.sendBeacon` en lotes de hasta 20. `sendBeacon` solo confirma que el
 *   navegador ha aceptado el envío, no que el servidor lo haya recibido. Si no puede encolarlo, los eventos vuelven a
 *   la cola. Un lote que ya está en una petición `fetch` no se repite por *beacon*.
 * - **SSR**: nada toca `window`, `document` ni `navigator` hasta el primer `track` en el navegador; en el servidor
 *   `track` no hace nada. Los listeners se registran una sola vez (módulo único, inmune al doble montaje de Strict Mode).
 *
 * Destino: `NEXT_PUBLIC_TELEMETRY_ENDPOINT` (se incrusta al compilar). Sin ella la telemetría queda desactivada.
 */
import { readToken } from "@/lib/session";
import {
  ALLOWLIST,
  type FrontendEventProperties,
  type FrontendEventType,
  isFrontendEventType,
} from "@/lib/telemetryCatalog";
import { currentTelemetrySessionId, newUuid, takeFormRequestId } from "@/lib/telemetrySession";

export type TelemetryEnvironment = "development" | "test" | "production";

export interface TelemetryEvent {
  eventId: string;
  timestamp: string;
  sessionId: string | null;
  userId: null;
  event_type: FrontendEventType;
  schemaVersion: string;
  requestId: string | null;
  source: "frontend";
  environment: TelemetryEnvironment;
  properties: Record<string, unknown>;
}

type DropReason = FrontendEventProperties["telemetry_events_dropped"]["drop_reason"];
type SendOutcome = "ok" | "retry" | "reject";

export interface TelemetryOptions {
  /** URL del receptor (`POST`). Sin ella, `track` no hace nada. */
  endpoint: string | undefined;
  environment: TelemetryEnvironment;
  flushIntervalMs?: number;
  maxBatchSize?: number;
  maxRetries?: number;
  baseBackoffMs?: number;
  /** Tope de la cola: si la API está caída mucho tiempo, se descartan los más antiguos (contados). */
  maxQueueSize?: number;
  /** Corte de cada intento de envío. */
  requestTimeoutMs?: number;
  /** Dependencias del navegador; sustituibles en los tests. */
  fetchImpl?: typeof fetch;
  getToken?: () => string | null;
  getSessionId?: () => string | null;
  now?: () => number;
}

interface Batch {
  events: TelemetryEvent[];
  /** Intentos hechos (el primero incluido). */
  attempts: number;
  /** Hay una petición `fetch` de este lote en curso. */
  sending: boolean;
  retryTimer: ReturnType<typeof setTimeout> | null;
  firstAttemptAt: number;
}

export const DEFAULTS = {
  flushIntervalMs: 10_000,
  maxBatchSize: 20,
  maxRetries: 3,
  baseBackoffMs: 1_000,
  maxQueueSize: 200,
  requestTimeoutMs: 10_000,
} as const;

export class TelemetryService {
  private readonly options: Required<Omit<TelemetryOptions, "endpoint" | "fetchImpl">> & {
    endpoint: string | undefined;
    fetchImpl: typeof fetch | undefined;
  };
  private queue: TelemetryEvent[] = [];
  private inFlight: Batch | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private listening = false;
  private warnedDisabled = false;

  constructor(options: TelemetryOptions) {
    this.options = {
      ...DEFAULTS,
      getToken: readToken,
      getSessionId: currentTelemetrySessionId,
      now: Date.now,
      ...options,
      fetchImpl: options.fetchImpl,
    };
  }

  /** Captura un evento del catálogo. No lanza nunca y no bloquea: el envío ocurre después, en lote. */
  track<T extends FrontendEventType>(eventType: T, properties: FrontendEventProperties[T]): void {
    if (typeof window === "undefined") return;
    if (!this.options.endpoint) {
      this.warnDisabled();
      return;
    }
    try {
      const event = this.buildEvent(eventType, properties as Record<string, unknown>);
      if (event) this.enqueue(event);
    } catch {
      // La telemetría nunca puede romper la pantalla que la usa.
    }
  }

  /** Eventos pendientes de envío (solo para los tests). */
  get pendingCount(): number {
    return this.queue.length;
  }

  /** Quita timers y listeners (tests). */
  dispose(): void {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    if (this.inFlight?.retryTimer) clearTimeout(this.inFlight.retryTimer);
    this.flushTimer = null;
    this.inFlight = null;
    this.queue = [];
    if (this.listening) {
      window.removeEventListener("visibilitychange", this.onVisibilityChange);
      window.removeEventListener("pagehide", this.onPageHide);
      this.listening = false;
    }
  }

  // --- Construcción del evento -------------------------------------------------------------------------------

  private buildEvent(eventType: string, properties: Record<string, unknown>): TelemetryEvent | null {
    if (!isFrontendEventType(eventType)) {
      this.devWarn(`evento fuera del catálogo del frontend: ${eventType}`);
      return null;
    }
    const spec = ALLOWLIST[eventType];
    const keys = Object.keys(properties ?? {});
    const missing = spec.properties.filter((key) => !(key in properties));
    const extra = keys.filter((key) => !spec.properties.includes(key));
    const sessionId = this.options.getSessionId();
    if (missing.length > 0 || extra.length > 0 || (spec.requiresSession && !sessionId)) {
      this.devWarn(`evento ${eventType} descartado: no cumple su allowlist o necesita sesión`);
      this.recordDrops([eventType], "schema_validation_failed", 1);
      return null;
    }
    // Solo las claves de la allowlist, en su orden: nada que no esté en el contrato sale del navegador.
    const clean = Object.fromEntries(spec.properties.map((key) => [key, properties[key]]));
    return {
      eventId: newUuid(),
      timestamp: new Date(this.options.now()).toISOString(),
      sessionId,
      userId: null,
      event_type: eventType,
      schemaVersion: spec.schemaVersion,
      requestId: spec.hasRequestId ? this.requestIdFor(clean) : null,
      source: "frontend",
      environment: this.options.environment,
      properties: clean,
    };
  }

  /** `form_submitted`: el `X-Request-Id` de la petición del formulario; `null` si no hubo respuesta. */
  private requestIdFor(properties: Record<string, unknown>): string | null {
    const id = takeFormRequestId(String(properties.form_id));
    return properties.outcome === "network_error" ? null : id;
  }

  // --- Cola y lotes ------------------------------------------------------------------------------------------

  /**
   * `internal`: aviso de descarte. No respeta el tope (lo supera como mucho en un aviso por tipo): si desplazara otro
   * evento, ese descarte generaría otro aviso, y así hasta vaciar la cola.
   */
  private enqueue(event: TelemetryEvent, internal = false): void {
    this.ensureListeners();
    if (!internal && this.queue.length >= this.options.maxQueueSize) {
      const [oldest] = this.queue.splice(0, 1);
      this.recordDrops([oldest.event_type], "buffer_overflow", 1);
    }
    this.queue.push(event);
    if (this.queue.length >= this.options.maxBatchSize) this.flush();
    else this.scheduleFlush();
  }

  private scheduleFlush(): void {
    if (this.flushTimer || this.queue.length === 0) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      this.flush();
    }, this.options.flushIntervalMs);
  }

  /**
   * Saca de la cola el siguiente lote: hasta `maxBatchSize` eventos consecutivos de la misma sesión. Así un lote nunca
   * mezcla sesiones y el receptor no puede atribuir eventos de una sesión al usuario de otra.
   */
  private takeBatch(): TelemetryEvent[] {
    const sessionId = this.queue[0]?.sessionId ?? null;
    let size = 0;
    while (
      size < this.queue.length &&
      size < this.options.maxBatchSize &&
      (this.queue[size].sessionId ?? null) === sessionId
    ) {
      size++;
    }
    return this.queue.splice(0, size);
  }

  /** Envía el siguiente lote si no hay otro en vuelo. Los demás esperan en la cola: no se duplica nada. */
  private flush(): void {
    if (this.inFlight || this.queue.length === 0) return;
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    const batch: Batch = {
      events: this.takeBatch(),
      attempts: 0,
      sending: false,
      retryTimer: null,
      firstAttemptAt: this.options.now(),
    };
    this.inFlight = batch;
    void this.attempt(batch);
  }

  private async attempt(batch: Batch): Promise<void> {
    batch.attempts += 1;
    batch.sending = true;
    const outcome = await this.post(batch.events);
    batch.sending = false;
    // Mientras tanto la página se ocultó y el lote salió por beacon (solo si estaba esperando un reintento).
    if (this.inFlight !== batch) return;

    if (outcome === "retry" && batch.attempts <= this.options.maxRetries) {
      const delay = this.options.baseBackoffMs * 2 ** (batch.attempts - 1);
      batch.retryTimer = setTimeout(() => {
        batch.retryTimer = null;
        void this.attempt(batch);
      }, delay);
      return;
    }

    this.inFlight = null;
    if (outcome !== "ok") {
      const seconds = Math.max(1, Math.ceil((this.options.now() - batch.firstAttemptAt) / 1000));
      this.recordDrops(
        batch.events.map((event) => event.event_type),
        outcome === "reject" ? "schema_validation_failed" : "delivery_failed",
        seconds
      );
    }
    // Lo que se acumuló mientras tanto: otro lote ya si está lleno; si no, al cumplirse el intervalo.
    if (this.queue.length >= this.options.maxBatchSize) this.flush();
    else this.scheduleFlush();
  }

  private async post(events: TelemetryEvent[]): Promise<SendOutcome> {
    const fetchImpl = this.options.fetchImpl ?? globalThis.fetch;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    // El token solo acompaña a eventos de la sesión actual: el receptor pone con él el `userId`.
    const sessionId = events[0]?.sessionId ?? null;
    const token = this.options.getToken();
    if (token && sessionId && sessionId === this.options.getSessionId()) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.requestTimeoutMs);
    try {
      const response = await fetchImpl(this.options.endpoint as string, {
        method: "POST",
        headers,
        body: JSON.stringify({ events }),
        keepalive: true,
        signal: controller.signal,
      });
      if (response.ok) return "ok";
      if (response.status === 408 || response.status === 429 || response.status >= 500) return "retry";
      return "reject";
    } catch {
      return "retry";
    } finally {
      clearTimeout(timer);
    }
  }

  // --- Descartes ---------------------------------------------------------------------------------------------

  /**
   * Cuenta los eventos descartados en `telemetry_events_dropped` (uno por tipo afectado). Los descartes de esos mismos
   * avisos no se vuelven a contar: con el receptor caído no se generaría una cadena infinita.
   */
  private recordDrops(eventTypes: string[], reason: DropReason, windowSeconds: number): void {
    const counts = new Map<string, number>();
    for (const type of eventTypes) {
      if (type !== "telemetry_events_dropped") counts.set(type, (counts.get(type) ?? 0) + 1);
    }
    for (const [type, count] of counts) {
      const event = this.buildEvent("telemetry_events_dropped", {
        component: "frontend_emitter",
        drop_reason: reason,
        affected_event_type: isFrontendEventType(type) ? type : "unknown",
        dropped_count: count,
        window_seconds: Math.min(windowSeconds, 86_400),
      });
      if (event) this.enqueue(event, true);
    }
  }

  // --- Página oculta: sendBeacon -----------------------------------------------------------------------------

  private ensureListeners(): void {
    if (this.listening || typeof window === "undefined") return;
    // En `window` y en fase de burbuja: se ejecuta después de los listeners de `document`, así los eventos que otros
    // módulos capturan al ocultarse la página (Web Vitals, formularios abandonados) ya están en la cola.
    window.addEventListener("visibilitychange", this.onVisibilityChange);
    window.addEventListener("pagehide", this.onPageHide);
    this.listening = true;
  }

  private readonly onVisibilityChange = (): void => {
    if (document.visibilityState === "hidden") this.flushWithBeacon();
  };

  private readonly onPageHide = (): void => this.flushWithBeacon();

  private flushWithBeacon(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    const canBeacon = typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function";
    if (!canBeacon) {
      this.flush(); // sin beacon: un `fetch` con `keepalive`, que también sobrevive al cierre de la página
      return;
    }

    const pending: TelemetryEvent[] = [];
    // Un lote esperando su reintento sale ahora por beacon; uno con un `fetch` en curso, no (se duplicaría).
    if (this.inFlight && !this.inFlight.sending) {
      if (this.inFlight.retryTimer) clearTimeout(this.inFlight.retryTimer);
      pending.push(...this.inFlight.events);
      this.inFlight = null;
    }
    pending.push(...this.queue.splice(0));

    const unsent: TelemetryEvent[] = [];
    for (let start = 0; start < pending.length; start += this.options.maxBatchSize) {
      const chunk = pending.slice(start, start + this.options.maxBatchSize);
      // `text/plain`: tipo «simple» de CORS, sin petición previa (un beacon no puede hacerla). El receptor lo lee
      // como JSON.
      const body = new Blob([JSON.stringify({ events: chunk })], { type: "text/plain;charset=UTF-8" });
      let queued = false;
      try {
        queued = navigator.sendBeacon(this.options.endpoint as string, body);
      } catch {
        queued = false;
      }
      if (!queued) unsent.push(...chunk);
    }
    // No se pudo ni encolar: vuelven a la cola para el siguiente envío normal (si la página sigue viva).
    if (unsent.length > 0) {
      this.queue.unshift(...unsent);
      this.queue.splice(this.options.maxQueueSize);
      this.scheduleFlush();
    }
  }

  // --- Avisos de desarrollo ----------------------------------------------------------------------------------

  private warnDisabled(): void {
    if (this.warnedDisabled || this.options.environment === "production") return;
    this.warnedDisabled = true;
    console.info("[telemetría] NEXT_PUBLIC_TELEMETRY_ENDPOINT no está definida: la telemetría está desactivada.");
  }

  private devWarn(message: string): void {
    if (this.options.environment !== "production") console.warn(`[telemetría] ${message}`);
  }
}

function resolveEnvironment(): TelemetryEnvironment {
  const explicit = process.env.NEXT_PUBLIC_TELEMETRY_ENVIRONMENT;
  if (explicit === "development" || explicit === "test" || explicit === "production") return explicit;
  if (process.env.NODE_ENV === "production") return "production";
  return process.env.NODE_ENV === "test" ? "test" : "development";
}

/** Instancia única del backoffice. */
const telemetry = new TelemetryService({
  endpoint: process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT?.trim() || undefined,
  environment: resolveEnvironment(),
});

/** Única función pública de captura de telemetría. */
export function track<T extends FrontendEventType>(eventType: T, properties: FrontendEventProperties[T]): void {
  telemetry.track(eventType, properties);
}
