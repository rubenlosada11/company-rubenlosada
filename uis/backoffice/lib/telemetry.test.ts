/**
 * `TelemetryService` (`lib/telemetry.ts`): envelope, allowlist, lotes de 10 s / 20 eventos, reintentos con backoff,
 * descarte, `sendBeacon` al ocultar la página y seguridad en SSR.
 *
 * Entorno `node` (sin jsdom): se simulan solo las fronteras con el navegador (`window` con sus eventos y
 * `localStorage`, `document.visibilityState`, `navigator.sendBeacon` y `fetch`). Temporizadores falsos de Jest.
 */
import { DEFAULTS, track, TelemetryService, type TelemetryEvent, type TelemetryOptions } from "@/lib/telemetry";
import { reserveFormRequestId } from "@/lib/telemetrySession";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const SESSION = "0b7e9c2a-5d4f-4a1b-8c3e-6f9d2a7b1c4e";
const OTHER_SESSION = "9f1d3c2b-7a6e-4d5c-8b4a-3e2f1d0c9b8a";
const ENDPOINT = "http://localhost:8000/telemetry/events";
const NOW = Date.UTC(2026, 10, 10, 18, 0, 0);

type FetchCall = { url: string; init: RequestInit; events: TelemetryEvent[]; resolve: (r: Response) => void; reject: (e: unknown) => void };

let fetchCalls: FetchCall[];
let beacons: { url: string; body: Blob }[];
let beaconResult: boolean;
let windowTarget: EventTarget;
let addListener: jest.SpyInstance;
let services: TelemetryService[];

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, value),
  };
}

function fakeFetch(url: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((resolve, reject) => {
    const events = (JSON.parse(String(init?.body)) as { events: TelemetryEvent[] }).events;
    fetchCalls.push({ url: String(url), init: init ?? {}, events, resolve, reject });
  });
}

const ok = () => new Response(JSON.stringify({ received: 1 }), { status: 200 });
const status = (code: number) => new Response("{}", { status: code });

function service(overrides: Partial<TelemetryOptions> = {}): TelemetryService {
  const created = new TelemetryService({
    endpoint: ENDPOINT,
    environment: "test",
    fetchImpl: fakeFetch as typeof fetch,
    getToken: () => "token-de-pruebas",
    getSessionId: () => SESSION,
    now: () => Date.now(),
    ...overrides,
  });
  services.push(created);
  return created;
}

function nav(t: TelemetryService, section: "dashboard" | "suppliers" = "dashboard") {
  t.track("navigation_section_viewed", { section, previous_section: null, navigation_trigger: "in_app_navigation" });
}

/** Deja correr las promesas pendientes (respuestas de `fetch`) sin adelantar los temporizadores. */
async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

function hide() {
  (globalThis as { document?: unknown }).document = { visibilityState: "hidden" };
  windowTarget.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  jest.useFakeTimers({ now: NOW });
  fetchCalls = [];
  beacons = [];
  beaconResult = true;
  services = [];
  windowTarget = new EventTarget();
  addListener = jest.spyOn(windowTarget, "addEventListener");
  Object.assign(windowTarget, { localStorage: memoryStorage() });
  Object.defineProperty(globalThis, "window", { value: windowTarget, configurable: true, writable: true });
  Object.defineProperty(globalThis, "navigator", {
    value: {
      sendBeacon: (url: string, body: Blob) => {
        beacons.push({ url, body });
        return beaconResult;
      },
    },
    configurable: true,
    writable: true,
  });
  jest.spyOn(console, "warn").mockImplementation(() => undefined);
  jest.spyOn(console, "info").mockImplementation(() => undefined);
});

afterEach(() => {
  services.forEach((s) => s.dispose());
  jest.useRealTimers();
  jest.restoreAllMocks();
  delete (globalThis as { window?: unknown }).window;
  delete (globalThis as { document?: unknown }).document;
});

describe("envelope", () => {
  it("construye todos los campos del contrato sin que los pase quien llama", async () => {
    const t = service();
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    const [event] = fetchCalls[0].events;
    expect(Object.keys(event).sort()).toEqual(
      [
        "environment",
        "eventId",
        "event_type",
        "properties",
        "requestId",
        "schemaVersion",
        "sessionId",
        "source",
        "timestamp",
        "userId",
      ].sort()
    );
    expect(event.eventId).toMatch(UUID_V4);
    expect(event.timestamp).toMatch(ISO_UTC);
    expect(event.timestamp).toBe(new Date(NOW).toISOString());
    expect(event).toMatchObject({
      sessionId: SESSION,
      userId: null, // lo pone el receptor a partir del token
      event_type: "navigation_section_viewed",
      schemaVersion: "1.0.0",
      requestId: null,
      source: "frontend",
      environment: "test",
      properties: { section: "dashboard", previous_section: null, navigation_trigger: "in_app_navigation" },
    });
  });

  it("cada evento tiene un eventId distinto", () => {
    const t = service();
    for (let i = 0; i < 20; i++) nav(t);
    const ids = new Set(fetchCalls[0].events.map((event) => event.eventId));
    expect(ids.size).toBe(20);
  });

  it("sessionId nulo fuera de sesión (páginas públicas)", () => {
    const t = service({ getSessionId: () => null });
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[0].events[0].sessionId).toBeNull();
  });

  it("form_submitted lleva el requestId de la petición del formulario; nulo si no hubo respuesta", () => {
    const t = service();
    const id = reserveFormRequestId("inventory_inbound");
    t.track("form_submitted", {
      form_id: "inventory_inbound",
      outcome: "success",
      http_status: 201,
      attempt_number: 1,
      duration_ms: 120.5,
    });
    reserveFormRequestId("inventory_outbound");
    t.track("form_submitted", {
      form_id: "inventory_outbound",
      outcome: "network_error",
      http_status: null,
      attempt_number: 2,
      duration_ms: null,
    });
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[0].events.map((event) => event.requestId)).toEqual([id, null]);
  });
});

describe("allowlist", () => {
  it("descarta un evento con propiedades de más y lo cuenta", () => {
    const t = service();
    t.track("navigation_section_viewed", {
      section: "dashboard",
      previous_section: null,
      navigation_trigger: "initial_load",
      email: "persona@example.com",
    } as never);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    const events = fetchCalls[0].events;
    expect(events).toHaveLength(1);
    expect(events[0].event_type).toBe("telemetry_events_dropped");
    expect(events[0].properties).toEqual({
      component: "frontend_emitter",
      drop_reason: "schema_validation_failed",
      affected_event_type: "navigation_section_viewed",
      dropped_count: 1,
      window_seconds: 1,
    });
    expect(JSON.stringify(events)).not.toContain("persona@example.com");
  });

  it("descarta un evento al que le falta una propiedad", () => {
    const t = service();
    t.track("form_started", { form_id: "inventory_inbound" } as never);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[0].events.map((event) => event.event_type)).toEqual(["telemetry_events_dropped"]);
  });

  it("ignora eventos fuera del catálogo del frontend (los de negocio los emite la API)", () => {
    const t = service();
    t.track("inbound_order_created" as never, {} as never);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs * 3);
    expect(fetchCalls).toHaveLength(0);
  });

  it("no emite un evento que exige sesión sin sesión", () => {
    const t = service({ getSessionId: () => null });
    t.track("session_ended", { end_reason: "user_logout", session_duration_seconds: 10 });
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[0].events.map((event) => event.event_type)).toEqual(["telemetry_events_dropped"]);
  });
});

describe("lotes", () => {
  it("no envía nada por evento: espera 10 s desde el primer evento pendiente", () => {
    const t = service();
    nav(t);
    jest.advanceTimersByTime(4_000);
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs - 4_000 - 1);
    expect(fetchCalls).toHaveLength(0);
    jest.advanceTimersByTime(1);
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].events).toHaveLength(2);
    expect(fetchCalls[0].url).toBe(ENDPOINT);
    expect(fetchCalls[0].init.method).toBe("POST");
    expect(fetchCalls[0].init.keepalive).toBe(true);
    expect(JSON.parse(String(fetchCalls[0].init.body))).toEqual({ events: fetchCalls[0].events });
  });

  it("envía en cuanto la cola llega a 20, sin esperar", () => {
    const t = service();
    for (let i = 0; i < 19; i++) nav(t);
    expect(fetchCalls).toHaveLength(0);
    nav(t);
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].events).toHaveLength(20);
  });

  it("un solo lote en vuelo: lo capturado mientras tanto va en el siguiente, sin duplicados", async () => {
    const t = service();
    for (let i = 0; i < 20; i++) nav(t);
    for (let i = 0; i < 25; i++) nav(t, "suppliers");
    expect(fetchCalls).toHaveLength(1);
    fetchCalls[0].resolve(ok());
    await settle();
    expect(fetchCalls).toHaveLength(2);
    expect(fetchCalls[1].events).toHaveLength(20);
    fetchCalls[1].resolve(ok());
    await settle();
    // Quedan 5: esperan al intervalo.
    expect(fetchCalls).toHaveLength(2);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[2].events).toHaveLength(5);
    const all = fetchCalls.flatMap((call) => call.events.map((event) => event.eventId));
    expect(new Set(all).size).toBe(45);
  });

  it("un lote nunca mezcla sesiones y el token solo acompaña a la sesión actual", async () => {
    let session = OTHER_SESSION;
    const t = service({ getSessionId: () => session });
    nav(t);
    session = SESSION;
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[0].events.map((e) => e.sessionId)).toEqual([OTHER_SESSION]);
    expect((fetchCalls[0].init.headers as Record<string, string>).Authorization).toBeUndefined();
    fetchCalls[0].resolve(ok());
    await settle();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls[1].events.map((e) => e.sessionId)).toEqual([SESSION]);
    expect((fetchCalls[1].init.headers as Record<string, string>).Authorization).toBe("Bearer token-de-pruebas");
  });

  it("con la cola llena descarta el evento más antiguo y lo cuenta", () => {
    const t = service({ maxQueueSize: 3, maxBatchSize: 50 });
    nav(t);
    nav(t);
    nav(t);
    nav(t, "suppliers");
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    // Se pierde el primero; el aviso de descarte entra sin desplazar a nadie (si no, se encadenarían descartes).
    expect(fetchCalls[0].events.map((e) => e.event_type)).toEqual([
      "navigation_section_viewed",
      "navigation_section_viewed",
      "telemetry_events_dropped",
      "navigation_section_viewed",
    ]);
    expect(fetchCalls[0].events[3].properties.section).toBe("suppliers");
  });
});

describe("reintentos", () => {
  it("reintenta 3 veces con backoff exponencial (1 s, 2 s, 4 s) y después descarta el lote", async () => {
    const t = service();
    nav(t);
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls).toHaveLength(1);

    for (const [attempt, delay] of [
      [1, 1_000],
      [2, 2_000],
      [3, 4_000],
    ]) {
      fetchCalls[attempt - 1].reject(new TypeError("Failed to fetch"));
      await settle();
      jest.advanceTimersByTime(delay - 1);
      expect(fetchCalls).toHaveLength(attempt);
      jest.advanceTimersByTime(1);
      expect(fetchCalls).toHaveLength(attempt + 1);
      expect(fetchCalls[attempt].events.map((e) => e.eventId)).toEqual(fetchCalls[0].events.map((e) => e.eventId));
    }

    fetchCalls[3].resolve(status(503));
    await settle();
    jest.advanceTimersByTime(60_000);
    // Tras 4 intentos (1 + 3 reintentos) no hay un quinto con el mismo lote: solo el aviso del descarte.
    expect(fetchCalls).toHaveLength(5);
    expect(fetchCalls[4].events).toHaveLength(1);
    expect(fetchCalls[4].events[0]).toMatchObject({
      event_type: "telemetry_events_dropped",
      properties: {
        drop_reason: "delivery_failed",
        affected_event_type: "navigation_section_viewed",
        dropped_count: 2,
        window_seconds: 7,
      },
    });
  });

  it("un reintento que va bien no duplica el lote", async () => {
    const t = service();
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    fetchCalls[0].resolve(status(500));
    await settle();
    nav(t, "suppliers"); // capturado mientras se espera el reintento: no bloquea ni se mezcla
    jest.advanceTimersByTime(1_000);
    expect(fetchCalls[1].events).toHaveLength(1);
    fetchCalls[1].resolve(ok());
    await settle();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls).toHaveLength(3);
    expect(fetchCalls[2].events.map((e) => e.properties.section)).toEqual(["suppliers"]);
  });

  it("un 4xx no se reintenta: el lote no es válido y repetirlo no lo arregla", async () => {
    const t = service();
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    fetchCalls[0].resolve(status(422));
    await settle();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls).toHaveLength(2);
    expect(fetchCalls[1].events[0].properties.drop_reason).toBe("schema_validation_failed");
  });

  it("si también falla el aviso del descarte, no genera más avisos", async () => {
    const t = service({ maxRetries: 0 });
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    fetchCalls[0].resolve(status(422));
    await settle();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    fetchCalls[1].resolve(status(422));
    await settle();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs * 5);
    expect(fetchCalls).toHaveLength(2);
  });
});

describe("sendBeacon al ocultar la página", () => {
  it("envía los pendientes en un lote text/plain y vacía la cola", async () => {
    const t = service();
    nav(t);
    nav(t, "suppliers");
    hide();
    expect(beacons).toHaveLength(1);
    expect(beacons[0].url).toBe(ENDPOINT);
    expect(beacons[0].body.type).toBe("text/plain;charset=utf-8");
    const body = JSON.parse(await beacons[0].body.text()) as { events: TelemetryEvent[] };
    expect(body.events.map((e) => e.properties.section)).toEqual(["dashboard", "suppliers"]);
    expect(t.pendingCount).toBe(0);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs * 2);
    expect(fetchCalls).toHaveLength(0);
  });

  it("parte los pendientes en lotes de 20", () => {
    const t = service({ maxBatchSize: 20 });
    // 20 salen por fetch; los 30 siguientes esperan en la cola mientras ese lote está en vuelo.
    for (let i = 0; i < 50; i++) nav(t);
    hide();
    expect(beacons).toHaveLength(2);
  });

  it("un lote que esperaba un reintento sale por beacon y su reintento se cancela", async () => {
    const t = service();
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    fetchCalls[0].reject(new TypeError("Failed to fetch"));
    await settle();
    hide();
    expect(beacons).toHaveLength(1);
    jest.advanceTimersByTime(60_000);
    expect(fetchCalls).toHaveLength(1);
  });

  it("no repite por beacon un lote con un fetch en curso", async () => {
    const t = service();
    for (let i = 0; i < 20; i++) nav(t);
    nav(t, "suppliers");
    hide();
    const body = JSON.parse(await beacons[0].body.text()) as { events: TelemetryEvent[] };
    expect(body.events).toHaveLength(1);
    expect(body.events[0].properties.section).toBe("suppliers");
  });

  it("si el navegador no acepta el beacon, los eventos se conservan", () => {
    beaconResult = false;
    const t = service();
    nav(t);
    hide();
    expect(t.pendingCount).toBe(1);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs);
    expect(fetchCalls).toHaveLength(1);
  });

  it("sin sendBeacon recurre a fetch con keepalive", () => {
    Object.defineProperty(globalThis, "navigator", { value: {}, configurable: true, writable: true });
    const t = service();
    nav(t);
    hide();
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].init.keepalive).toBe(true);
  });

  it("registra sus listeners una sola vez", () => {
    const t = service();
    for (let i = 0; i < 5; i++) nav(t);
    const visibility = addListener.mock.calls.filter(([type]) => type === "visibilitychange");
    expect(visibility).toHaveLength(1);
  });
});

describe("configuración y SSR", () => {
  it("sin endpoint no hace nada", () => {
    const t = service({ endpoint: undefined });
    nav(t);
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs * 3);
    hide();
    expect(fetchCalls).toHaveLength(0);
    expect(beacons).toHaveLength(0);
    expect(t.pendingCount).toBe(0);
  });

  it("en el servidor (sin window) no toca APIs del navegador ni lanza", () => {
    delete (globalThis as { window?: unknown }).window;
    const sendBeacon = jest.fn();
    Object.defineProperty(globalThis, "navigator", { value: { sendBeacon }, configurable: true, writable: true });
    const t = service();
    expect(() => nav(t)).not.toThrow();
    expect(() => track("form_started", { form_id: "login", section: "login" })).not.toThrow();
    jest.advanceTimersByTime(DEFAULTS.flushIntervalMs * 3);
    expect(fetchCalls).toHaveLength(0);
    expect(sendBeacon).not.toHaveBeenCalled();
    expect(t.pendingCount).toBe(0);
  });
});
