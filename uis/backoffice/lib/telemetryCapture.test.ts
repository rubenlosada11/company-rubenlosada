/**
 * Piezas de la captura transversal: secciones y plantillas de ruta (nunca URLs), errores de JavaScript (nombre y
 * huella, nunca mensaje ni traza; agregación por huella) y fallos de comunicación con la API (agregación de 30 s),
 * identificadores de sesión y resultado de los envíos de formularios.
 */
import { ApiError } from "@/lib/http";
import { track } from "@/lib/telemetry";
import {
  captureFrontendError,
  ERROR_WINDOW_MS,
  errorKind,
  errorName,
  firstOwnFrame,
  reportRequestFailure,
  REQUEST_FAILURE_WINDOW_MS,
} from "@/lib/telemetryCapture";
import { apiRouteTemplate, sectionFor } from "@/lib/telemetrySections";
import {
  beginTelemetrySession,
  clearTelemetrySession,
  commitTelemetrySession,
  currentTelemetrySession,
  currentTelemetrySessionId,
  discardPendingTelemetrySession,
  isUuidV4,
  newUuid,
  reserveFormRequestId,
  takeFormRequestId,
  TELEMETRY_SESSION_KEY,
} from "@/lib/telemetrySession";
import { submitOutcome } from "@/lib/useFormTelemetry";

jest.mock("./telemetry", () => ({ track: jest.fn() }));

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

let tracked: [string, Record<string, unknown>][];

beforeEach(() => {
  tracked = [];
  jest.mocked(track).mockImplementation((type, props) => {
    tracked.push([type, props as Record<string, unknown>]);
  });
  Object.defineProperty(globalThis, "window", {
    value: { localStorage: memoryStorage(), location: { origin: "https://backoffice.test", pathname: "/inventory/orders" } },
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
  delete (globalThis as { window?: unknown }).window;
});

describe("sectionFor", () => {
  it.each([
    ["/", "dashboard"],
    ["/inventory", "inventory_products"],
    ["/inventory/orders/outbound", "inventory_outbound"],
    ["/inventory/orders/inbound?sku_id=4", "inventory_inbound"],
    ["/reset-password?token=secreto", "reset_password"],
    ["/proveedores/", "suppliers"],
    ["/ruta-que-no-existe", "not_found"],
  ])("%s → %s", (path, section) => {
    expect(sectionFor(path)).toBe(section);
  });
});

describe("apiRouteTemplate", () => {
  it.each([
    ["/inventory/products/12", "/inventory/products/{sku_id}"],
    ["/inventory/orders?warehouse=LA&sku_id=3", "/inventory/orders"],
    ["/api/incidents/summary", "/api/incidents/summary"],
    ["/api/incidents/abc-123/status", "/api/incidents/{incident_id}/status"],
    ["/suppliers/7/rate", "/suppliers/{supplier_id}/rate"],
    ["/otra/cosa", "unmatched"],
  ])("%s → %s", (path, template) => {
    expect(apiRouteTemplate(path)).toBe(template);
  });
});

describe("errores de JavaScript", () => {
  it("solo el nombre de la clase; nunca el mensaje", () => {
    expect(errorName(new TypeError("email persona@example.com"))).toBe("TypeError");
    expect(errorName({})).toBe("Object");
    expect(errorName("texto")).toBe("String"); // clase del valor rechazado, nunca su contenido
    expect(errorName(Object.assign(new Error("x"), { name: "nombre con espacios" }))).toBe("Error");
  });

  it("primer marco propio sin origen ni query", () => {
    const stack = [
      "TypeError: x",
      "    at f (https://cdn.externo.com/lib.js:1:1)",
      "    at g (https://backoffice.test/_next/static/chunks/page-1a2b.js?v=3:10:200)",
    ].join("\n");
    expect(firstOwnFrame(stack, "https://backoffice.test")).toBe("/_next/static/chunks/page-1a2b.js:10:200");
  });

  it("clasifica los fallos de carga de chunks", () => {
    const chunk = Object.assign(new Error("Loading chunk 42 failed."), { name: "ChunkLoadError" });
    expect(errorKind(chunk, "render_error")).toBe("chunk_load_error");
    expect(errorKind(new TypeError("x"), "render_error")).toBe("render_error");
  });

  it("emite el primero al momento y agrupa los repetidos de la misma huella", async () => {
    jest.useFakeTimers();
    const error = () => {
      const e = new TypeError("Cannot read properties of undefined (reading 'email')");
      e.stack = "TypeError: x\n    at h (https://backoffice.test/_next/static/chunks/a.js:1:2)";
      return e;
    };
    await captureFrontendError(error(), "panel", "render_error");
    await captureFrontendError(error(), "none", "uncaught_exception");
    await captureFrontendError(error(), "none", "uncaught_exception");
    expect(tracked).toHaveLength(1);
    const [type, props] = tracked[0];
    expect(type).toBe("frontend_error_captured");
    expect(props).toMatchObject({
      error_kind: "render_error",
      error_name: "TypeError",
      boundary: "panel",
      section: "inventory_orders",
      digest: null,
      app_version: "dev",
      occurrence_count: 1,
    });
    expect(props.fingerprint).toMatch(/^[0-9a-f]{16}$/);
    expect(JSON.stringify(props)).not.toContain("email");
    await jest.advanceTimersByTimeAsync(ERROR_WINDOW_MS);
    expect(tracked).toHaveLength(2);
    expect(tracked[1][1].occurrence_count).toBe(2);
  });

  it("un mismo objeto de error capturado por dos vías cuenta una vez", async () => {
    const error = new RangeError("x");
    await Promise.all([
      captureFrontendError(error, "panel", "render_error"),
      captureFrontendError(error, "none", "uncaught_exception"),
    ]);
    expect(tracked).toHaveLength(1);
  });
});

describe("fallos de comunicación con la API", () => {
  it("plantilla de ruta y agregación de 30 s por ruta y tipo", () => {
    jest.useFakeTimers();
    reportRequestFailure("network_error", "/inventory/products/5", "GET");
    reportRequestFailure("network_error", "/inventory/products/9", "GET");
    reportRequestFailure("timeout", "/inventory/orders?warehouse=LA", "GET");
    expect(tracked.map(([, props]) => props)).toEqual([
      {
        failure_kind: "network_error",
        api_route: "/inventory/products/{sku_id}",
        http_method: "GET",
        section: "inventory_orders",
      },
      { failure_kind: "timeout", api_route: "/inventory/orders", http_method: "GET", section: "inventory_orders" },
    ].map((props) => ({ ...props, occurrence_count: 1 })));
    jest.advanceTimersByTime(REQUEST_FAILURE_WINDOW_MS);
    expect(tracked).toHaveLength(3);
    expect(tracked[2][1]).toMatchObject({ api_route: "/inventory/products/{sku_id}", occurrence_count: 1 });
  });
});

describe("sesión de telemetría", () => {
  it("nace pendiente en el login, se confirma y se borra al cerrar", () => {
    const id = beginTelemetrySession();
    expect(isUuidV4(id)).toBe(true);
    expect(currentTelemetrySessionId()).toBe(id); // viaja en el X-Session-Id del propio login
    commitTelemetrySession();
    expect(currentTelemetrySession()?.id).toBe(id);
    expect(JSON.parse(window.localStorage.getItem(TELEMETRY_SESSION_KEY) ?? "{}").id).toBe(id);
    clearTelemetrySession();
    expect(currentTelemetrySessionId()).toBeNull();
  });

  it("un login fallido no deja sesión", () => {
    beginTelemetrySession();
    discardPendingTelemetrySession();
    expect(currentTelemetrySessionId()).toBeNull();
  });

  it("una sesión nueva tiene otro id", () => {
    const first = beginTelemetrySession();
    commitTelemetrySession();
    const second = beginTelemetrySession();
    commitTelemetrySession();
    expect(second).not.toBe(first);
    expect(currentTelemetrySessionId()).toBe(second);
  });

  it("el requestId reservado por un formulario se usa una sola vez", () => {
    const id = reserveFormRequestId("inventory_inbound");
    expect(takeFormRequestId("inventory_inbound")).toBe(id);
    expect(takeFormRequestId("inventory_inbound")).toBeNull();
  });

  it("UUID v4 también sin crypto.randomUUID", () => {
    const original = globalThis.crypto.randomUUID;
    Object.defineProperty(globalThis.crypto, "randomUUID", { value: undefined, configurable: true });
    try {
      expect(isUuidV4(newUuid())).toBe(true);
    } finally {
      Object.defineProperty(globalThis.crypto, "randomUUID", { value: original, configurable: true });
    }
  });
});

describe("resultado de un envío de formulario", () => {
  it.each([
    [null, "success", null],
    [new ApiError("sin conexión", 0), "network_error", null],
    [new ApiError("caducada", 401), "unauthorized", 401],
    [new ApiError("stock", 400), "business_rejection", 400],
    [new ApiError("no existe", 404), "business_rejection", 404],
    [new ApiError("campos", 422), "validation_error", 422],
    [new ApiError("servidor", 503), "server_error", 503],
    [new TypeError("x"), "network_error", null],
  ])("%p → %s", (error, outcome, httpStatus) => {
    expect(submitOutcome(error)).toEqual({ outcome, httpStatus });
  });
});
