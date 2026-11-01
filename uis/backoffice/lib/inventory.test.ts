/**
 * Hito 5 — capa de integración del inventario (`lib/inventory.ts`) sobre el cliente común (`lib/http.ts`).
 *
 * `fetch` se sustituye por un doble que devuelve respuestas como las de la API real (`services/api`, mismas formas y
 * mensajes); `window` se simula solo en lo que usa `lib/http.ts` (el token en `localStorage` y el aviso de 401).
 */
import type { ApiError } from "@/lib/http";
import type * as InventoryModule from "@/lib/inventory";
import { TOKEN_KEY, UNAUTHORIZED_EVENT } from "@/lib/session";
import type { Product } from "@/types/inventory";

const PRODUCT: Product = {
  id: 2,
  name: "Zapatilla blanca clásica - Talla 42",
  sku: "CLT-SNK-W-42-Z",
  client_name: "PureStep Footwear",
  category: "fashion",
  warehouse: "ZGZ",
  current_stock: 28,
  stock_by_warehouse: { LA: 0, ZGZ: 28 },
};

const SKU_SUMMARY = {
  id: 2,
  name: PRODUCT.name,
  sku: PRODUCT.sku,
  client_name: PRODUCT.client_name,
  category: PRODUCT.category,
  warehouse: PRODUCT.warehouse,
};

const EXIT = {
  id: 5,
  sku_id: 2,
  quantity: 3,
  exit_type: "loss",
  tracking_number: null,
  warehouse: "ZGZ",
  created_at: "2026-11-01T18:25:27.646840Z",
  user_uuid: "c4eddc7a-a9e0-45a7-b9c5-1b45609a71bf",
};

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: jest.Mock;
let events: string[];
let storage: Map<string, string>;

function withWindow() {
  storage = new Map([[TOKEN_KEY, "token-de-prueba"]]);
  events = [];
  const localStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => void storage.set(key, value),
    removeItem: (key: string) => void storage.delete(key),
  };
  Object.defineProperty(globalThis, "window", {
    value: { localStorage, dispatchEvent: (event: Event) => events.push(event.type) },
    configurable: true,
    writable: true,
  });
}

/** Carga el módulo con las variables de entorno indicadas (se leen al importar, como en `next build`). */
async function load(env: { base?: string; inventory?: string } = { base: "http://api.test" }) {
  jest.resetModules();
  process.env.NEXT_PUBLIC_API_BASE_URL = env.base ?? "";
  process.env.NEXT_PUBLIC_INVENTORY_API_URL = env.inventory ?? "";
  const inventory: typeof InventoryModule = await import("@/lib/inventory");
  const http = await import("@/lib/http");
  return { ...inventory, ApiError: http.ApiError };
}

beforeEach(() => {
  withWindow();
  fetchMock = jest.fn();
  global.fetch = fetchMock;
});

afterAll(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe("inventoryApi — peticiones", () => {
  it("lista los productos con el Bearer de la sesión y la URL del inventario", async () => {
    const { inventoryApi } = await load({ base: "http://api.test", inventory: "http://inventario.test/" });
    fetchMock.mockResolvedValue(json(200, [PRODUCT]));

    await expect(inventoryApi.listProducts()).resolves.toEqual([PRODUCT]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://inventario.test/inventory/products");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-de-prueba");
  });

  it("sin NEXT_PUBLIC_INVENTORY_API_URL usa NEXT_PUBLIC_API_BASE_URL", async () => {
    const { inventoryApi } = await load({ base: "http://api.test" });
    fetchMock.mockResolvedValue(json(200, PRODUCT));

    await inventoryApi.getProduct(2);

    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/inventory/products/2");
  });

  it("sin ninguna URL configurada falla con un ApiError legible y sin llamar a la red", async () => {
    const { inventoryApi, ApiError: Err } = await load({});
    const error = await inventoryApi.listProducts().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Err);
    expect((error as ApiError).status).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("envía la entrada con el cuerpo exacto del contrato", async () => {
    const { inventoryApi } = await load();
    const entry = { ...EXIT, reference: "PO-2024-0098" };
    delete (entry as Partial<typeof EXIT>).exit_type;
    delete (entry as Partial<typeof EXIT>).tracking_number;
    fetchMock.mockResolvedValue(json(201, entry));

    await expect(inventoryApi.createInbound({ sku_id: 2, quantity: 40, reference: "PO-2024-0098" })).resolves.toEqual(
      entry
    );
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/inventory/orders/inbound");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ sku_id: 2, quantity: 40, reference: "PO-2024-0098" });
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-de-prueba");
  });

  it("envía la salida y devuelve el StockExit de la API", async () => {
    const { inventoryApi } = await load();
    fetchMock.mockResolvedValue(json(201, EXIT));
    const payload = { sku_id: 2, quantity: 3, exit_type: "loss" as const, tracking_number: null };

    await expect(inventoryApi.createOutbound(payload)).resolves.toEqual(EXIT);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/inventory/orders/outbound");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(payload);
  });

  it("pide el historial con los filtros de la API y acepta entradas y salidas", async () => {
    const { inventoryApi } = await load();
    const movements = [
      { ...EXIT, movement_type: "outbound", sku: SKU_SUMMARY },
      { ...EXIT, id: 1, exit_type: undefined, reference: "GR-LA-0234", movement_type: "inbound", sku: SKU_SUMMARY },
    ];
    fetchMock.mockResolvedValue(json(200, movements));

    await expect(inventoryApi.listOrders({ warehouse: "ZGZ", sku_id: "2" })).resolves.toHaveLength(2);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/inventory/orders?warehouse=ZGZ&sku_id=2");

    fetchMock.mockResolvedValue(json(200, []));
    await expect(inventoryApi.listOrders({ warehouse: "", sku_id: "" })).resolves.toEqual([]);
    expect(fetchMock.mock.calls[1][0]).toBe("http://api.test/inventory/orders");
  });

  it("una lista vacía es un resultado válido, no un error", async () => {
    const { inventoryApi } = await load();
    fetchMock.mockResolvedValue(json(200, []));
    await expect(inventoryApi.listProducts()).resolves.toEqual([]);
  });
});

describe("inventoryApi — respuestas inesperadas", () => {
  it.each([
    ["un objeto en lugar de una lista", { items: [PRODUCT] }],
    ["un producto sin current_stock", [{ ...PRODUCT, current_stock: undefined }]],
    ["un stock decimal", [{ ...PRODUCT, current_stock: 1.5 }]],
  ])("rechaza %s con un mensaje legible", async (_, body) => {
    const { inventoryApi, UNEXPECTED_RESPONSE_MESSAGE } = await load();
    fetchMock.mockResolvedValue(json(200, body));
    await expect(inventoryApi.listProducts()).rejects.toMatchObject({ message: UNEXPECTED_RESPONSE_MESSAGE });
  });

  it("rechaza un movimiento con un tipo desconocido", async () => {
    const { inventoryApi, UNEXPECTED_RESPONSE_MESSAGE } = await load();
    fetchMock.mockResolvedValue(json(200, [{ ...EXIT, movement_type: "transfer", sku: SKU_SUMMARY }]));
    await expect(inventoryApi.listOrders({ warehouse: "", sku_id: "" })).rejects.toMatchObject({
      message: UNEXPECTED_RESPONSE_MESSAGE,
    });
  });

  it("un 200 que no es JSON (página de un proxy) da un error legible, no un SyntaxError", async () => {
    const { inventoryApi, ApiError: Err } = await load();
    fetchMock.mockResolvedValue(new Response("<html>proxy</html>", { status: 200 }));
    const error = await inventoryApi.listProducts().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Err);
    expect((error as Error).message).not.toMatch(/Unexpected token|<html>/);
  });
});

describe("inventoryApi — errores HTTP", () => {
  it("400 de stock insuficiente: mensaje en español junto al campo quantity", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(
      json(400, { detail: "Insufficient stock for SKU 'CLT-SNK-W-42-Z'. Available: 28, requested: 99999." })
    );
    const error = await mod.inventoryApi
      .createOutbound({ sku_id: 2, quantity: 99999, exit_type: "loss", tracking_number: null })
      .catch((e: unknown) => e);

    expect(mod.parseInsufficientStock(error)).toEqual({ sku: "CLT-SNK-W-42-Z", available: 28, requested: 99999 });
    const expected = "Stock insuficiente para el SKU CLT-SNK-W-42-Z: hay 28 unidades disponibles y has pedido 99.999 unidades.";
    expect(mod.inventoryFieldErrors(error)).toEqual({ quantity: expected });
    expect(mod.inventoryErrorMessage(error, "registrar la salida")).toBe(expected);
    expect(events).toEqual([]);
  });

  it("422 del dispatch sin tracking_number: error en su campo, ya redactado para el usuario", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(
      json(422, {
        detail: [
          {
            type: "value_error",
            loc: ["body", "tracking_number"],
            msg: "Value error, tracking_number es obligatorio cuando exit_type es 'dispatch'",
          },
        ],
      })
    );
    const error = await mod.inventoryApi
      .createOutbound({ sku_id: 2, quantity: 1, exit_type: "dispatch", tracking_number: null })
      .catch((e: unknown) => e);

    expect(mod.inventoryFieldErrors(error)).toEqual({
      tracking_number: "El número de seguimiento es obligatorio en un despacho.",
    });
    expect(mod.inventoryErrorMessage(error, "registrar la salida")).toBe("Revisa los campos marcados y vuelve a intentarlo.");
  });

  it("401: borra el token, avisa para volver al login y da el mensaje de sesión caducada", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(json(401, { detail: "Not authenticated" }));
    const error = await mod.inventoryApi.listProducts().catch((e: unknown) => e);

    expect((error as ApiError).status).toBe(401);
    expect(storage.has(TOKEN_KEY)).toBe(false);
    expect(events).toEqual([UNAUTHORIZED_EVENT]);
    expect(mod.inventoryErrorMessage(error, "cargar los productos")).toBe(
      "Tu sesión ha caducado. Vuelve a iniciar sesión."
    );
  });

  it("403: mensaje de permisos, sin cerrar la sesión", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(new Response(null, { status: 403 }));
    const error = await mod.inventoryApi.listProducts().catch((e: unknown) => e);

    expect(storage.has(TOKEN_KEY)).toBe(true);
    expect(events).toEqual([]);
    expect(mod.inventoryErrorMessage(error, "cargar los productos")).toBe("No tienes permiso para hacer esta operación.");
  });

  it("404 del SKU: mensaje para actualizar el listado", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(json(404, { detail: "No existe ningún SKU con id 999." }));
    const error = await mod.inventoryApi.getProduct(999).catch((e: unknown) => e);
    expect(mod.inventoryErrorMessage(error, "consultar el stock")).toMatch(/ya no existe.*Actualiza el listado/);
  });

  it("500: mensaje genérico, sin el cuerpo de la respuesta", async () => {
    const mod = await load();
    fetchMock.mockResolvedValue(json(500, { detail: "Traceback: sqlalchemy.exc.OperationalError ..." }));
    const error = await mod.inventoryApi.listProducts().catch((e: unknown) => e);
    const message = mod.inventoryErrorMessage(error, "cargar los productos");

    expect(message).toBe(
      "No se ha podido cargar los productos por un problema del servidor. Inténtalo de nuevo en unos minutos."
    );
    expect(message).not.toMatch(/Traceback|sqlalchemy/);
    expect(mod.inventoryFieldErrors(error)).toEqual({});
  });

  it("error de red: ApiError con estado 0 y mensaje de conexión", async () => {
    const mod = await load();
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await mod.inventoryApi.listProducts().catch((e: unknown) => e);

    expect((error as ApiError).status).toBe(0);
    expect(mod.inventoryErrorMessage(error, "cargar los productos")).toMatch(/No se pudo conectar con la API/);
  });

  it("una petición cancelada (cambio de producto) se propaga como AbortError, no como error de la interfaz", async () => {
    const mod = await load();
    fetchMock.mockRejectedValue(new DOMException("Aborted", "AbortError"));
    const error = await mod.inventoryApi.getProduct(2, new AbortController().signal).catch((e: unknown) => e);
    expect((error as Error).name).toBe("AbortError");
  });
});

describe("stockLevel — umbrales de presentación", () => {
  it.each([
    [-1, "out"],
    [0, "out"],
    [1, "critical"],
    [10, "critical"],
    [11, "low"],
    [30, "low"],
    [31, "healthy"],
    [117, "healthy"],
  ] as const)("%p unidades → %p", async (stock, level) => {
    const { stockLevel } = await load();
    expect(stockLevel(stock)).toBe(level);
  });
});

describe("parseQuantity", () => {
  it.each([
    ["1", 1],
    [" 40 ", 40],
    ["2147483647", 2147483647],
  ])("acepta %p", async (text, expected) => {
    const { parseQuantity } = await load();
    expect(parseQuantity(text)).toBe(expected);
  });

  it.each(["", "0", "-3", "1.5", "1,5", "5e2", "abc", "2147483648"])("rechaza %p", async (text) => {
    const { parseQuantity } = await load();
    expect(parseQuantity(text)).toBeNull();
  });
});

describe("validateInboundDraft", () => {
  it("con datos válidos construye el cuerpo de la API (sin warehouse: el del SKU)", async () => {
    const { validateInboundDraft } = await load();
    expect(validateInboundDraft({ skuId: "3", quantity: "25", reference: "  PO-2024-0098 " })).toEqual({
      errors: {},
      payload: { sku_id: 3, quantity: 25, reference: "PO-2024-0098" },
    });
  });

  it("vacío: producto, cantidad y referencia obligatorios", async () => {
    const { validateInboundDraft, EMPTY_INBOUND_DRAFT } = await load();
    const { payload, errors } = validateInboundDraft(EMPTY_INBOUND_DRAFT);
    expect(payload).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["quantity", "reference", "sku_id"]);
  });

  it.each([
    ["0", "La cantidad debe ser un número entero mayor que 0."],
    ["2,5", "La cantidad debe ser un número entero mayor que 0."],
    ["99999999999", "La cantidad no puede superar 2.147.483.647."],
  ])("cantidad %p no válida", async (quantity, message) => {
    const { validateInboundDraft } = await load();
    expect(validateInboundDraft({ skuId: "1", quantity, reference: "PO-1" }).errors).toEqual({ quantity: message });
  });

  it("referencia de más de 64 caracteres", async () => {
    const { validateInboundDraft } = await load();
    const { errors } = validateInboundDraft({ skuId: "1", quantity: "1", reference: "x".repeat(65) });
    expect(Object.keys(errors)).toEqual(["reference"]);
  });
});

describe("validateOutboundDraft", () => {
  const dispatch = { skuId: "2", quantity: "5", exitType: "dispatch" as const, trackingNumber: " 1Z999AA10123456784 " };

  it("despacho válido lleva el tracking_number recortado", async () => {
    const { validateOutboundDraft } = await load();
    expect(validateOutboundDraft(dispatch, 28).payload).toEqual({
      sku_id: 2,
      quantity: 5,
      exit_type: "dispatch",
      tracking_number: "1Z999AA10123456784",
    });
  });

  it("una pérdida envía tracking_number nulo aunque se hubiera escrito antes", async () => {
    const { validateOutboundDraft } = await load();
    expect(validateOutboundDraft({ ...dispatch, exitType: "loss" }, 28).payload?.tracking_number).toBeNull();
  });

  it("despacho sin número de seguimiento", async () => {
    const { validateOutboundDraft } = await load();
    expect(validateOutboundDraft({ ...dispatch, trackingNumber: "  " }, 28).errors).toEqual({
      tracking_number: "El número de seguimiento es obligatorio en un despacho.",
    });
  });

  it.each([
    [27, true],
    [28, true],
    [29, false],
  ])("cantidad %p con 28 disponibles → válida: %p", async (quantity, valid) => {
    const { validateOutboundDraft } = await load();
    const { payload, errors } = validateOutboundDraft({ ...dispatch, quantity: String(quantity) }, 28);
    expect(payload !== null).toBe(valid);
    if (!valid) expect(errors.quantity).toBe("La cantidad supera el stock disponible (28 unidades).");
  });

  it("con stock agotado cualquier cantidad supera el disponible", async () => {
    const { validateOutboundDraft } = await load();
    expect(validateOutboundDraft({ ...dispatch, quantity: "1" }, 0).errors.quantity).toBe(
      "La cantidad supera el stock disponible (0 unidades)."
    );
  });

  it("sin un stock fiable (cargando o con error) no bloquea por stock: decide la API", async () => {
    const { validateOutboundDraft } = await load();
    expect(validateOutboundDraft({ ...dispatch, quantity: "9999" }, null).payload).not.toBeNull();
  });

  it("vacío: producto, tipo y cantidad obligatorios", async () => {
    const { validateOutboundDraft, EMPTY_OUTBOUND_DRAFT } = await load();
    expect(Object.keys(validateOutboundDraft(EMPTY_OUTBOUND_DRAFT, null).errors).sort()).toEqual([
      "exit_type",
      "quantity",
      "sku_id",
    ]);
  });
});

describe("formato", () => {
  it("productOptionLabel distingue el mismo nombre en dos almacenes", async () => {
    const { productOptionLabel } = await load();
    expect(productOptionLabel(PRODUCT)).toBe("Zapatilla blanca clásica - Talla 42 · CLT-SNK-W-42-Z · Zaragoza (ZGZ)");
  });

  it("formatMovementDate no rompe con una fecha no válida", async () => {
    const { formatMovementDate } = await load();
    expect(formatMovementDate("no-es-una-fecha")).toBe("Fecha no disponible");
    expect(formatMovementDate(EXIT.created_at)).toMatch(/2026/);
  });

  it("parseSkuId solo acepta ids enteros positivos (p. ej. de ?sku_id=)", async () => {
    const { parseSkuId } = await load();
    expect(parseSkuId("3")).toBe(3);
    for (const value of [null, "", "0", "-1", "2.5", "abc", "99999999999999999999"]) {
      expect(parseSkuId(value)).toBeNull();
    }
  });
});
