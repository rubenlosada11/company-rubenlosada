/**
 * Inventario unificado (`/inventory` en services/api, Hito 5). Único punto del backoffice que habla con esa API: los
 * componentes usan `inventoryApi` y nunca llaman a `fetch`.
 *
 * La petición la hace `lib/http.ts`, el cliente común del backoffice: añade `Authorization: Bearer <token>` (el token
 * de la sesión, en `localStorage`), cierra la sesión ante un 401, corta a los 20 s y convierte las respuestas de error
 * en `ApiError`. Aquí se añaden la URL propia del inventario, la comprobación de la forma de las respuestas, las
 * validaciones de los formularios (las mismas reglas que la API, que es quien decide) y los mensajes de error.
 */
import { ApiError, apiErrorMessage, http, type ApiOptions } from "@/lib/http";
import type {
  ExitType,
  Movement,
  MovementFilters,
  Product,
  ProductSummary,
  StockEntry,
  StockEntryPayload,
  StockExit,
  StockExitPayload,
} from "@/types/inventory";
import { warehouseLabel } from "@/lib/data/inventory";

/**
 * `NEXT_PUBLIC_INVENTORY_API_URL` (se incrusta al compilar). Vacía o sin definir: `NEXT_PUBLIC_API_BASE_URL`, porque
 * hoy el inventario vive en la misma API que el login y valida el mismo token.
 */
const INVENTORY_API_URL = process.env.NEXT_PUBLIC_INVENTORY_API_URL?.trim() || undefined;
const OPTIONS: ApiOptions = { baseUrl: INVENTORY_API_URL };

export const UNEXPECTED_RESPONSE_MESSAGE =
  "La API de inventario ha devuelto una respuesta inesperada. Inténtalo de nuevo y, si se repite, avisa al equipo técnico.";

// --- Comprobación de las respuestas ------------------------------------------------------------------------------
// La API está tipada, pero un proxy, una versión distinta o un error pueden devolver otra cosa con un 200. Se comprueban
// los campos que usa la interfaz; si faltan, se muestra un error legible en lugar de romper el render.

type Guard<T> = (value: unknown) => value is T;

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const isInteger = (value: unknown): value is number => Number.isInteger(value);
const isString = (value: unknown): value is string => typeof value === "string";

function isProductSummary(value: unknown): value is ProductSummary {
  return (
    isObject(value) &&
    isInteger(value.id) &&
    isString(value.name) &&
    isString(value.sku) &&
    isString(value.client_name) &&
    isString(value.category) &&
    isString(value.warehouse)
  );
}

export function isProduct(value: unknown): value is Product {
  if (!isProductSummary(value)) return false;
  const { current_stock, stock_by_warehouse } = value as Record<string, unknown>;
  return (
    isInteger(current_stock) &&
    isObject(stock_by_warehouse) &&
    isInteger(stock_by_warehouse.LA) &&
    isInteger(stock_by_warehouse.ZGZ)
  );
}

function isMovementBase(value: unknown): value is Record<string, unknown> {
  return (
    isObject(value) &&
    isInteger(value.id) &&
    isInteger(value.sku_id) &&
    isInteger(value.quantity) &&
    isString(value.warehouse) &&
    isString(value.created_at) &&
    isString(value.user_uuid)
  );
}

export function isStockEntry(value: unknown): value is StockEntry {
  return isMovementBase(value) && isString(value.reference);
}

export function isStockExit(value: unknown): value is StockExit {
  return (
    isMovementBase(value) &&
    (value.exit_type === "dispatch" || value.exit_type === "loss") &&
    (value.tracking_number === null || isString(value.tracking_number))
  );
}

export function isMovement(value: unknown): value is Movement {
  if (!isObject(value) || !isProductSummary(value.sku)) return false;
  if (value.movement_type === "inbound") return isStockEntry(value);
  if (value.movement_type === "outbound") return isStockExit(value);
  return false;
}

function expectItem<T>(value: unknown, guard: Guard<T>): T {
  if (!guard(value)) throw new ApiError(UNEXPECTED_RESPONSE_MESSAGE, 200);
  return value;
}

function expectList<T>(value: unknown, guard: Guard<T>): T[] {
  if (!Array.isArray(value) || !value.every(guard)) throw new ApiError(UNEXPECTED_RESPONSE_MESSAGE, 200);
  return value;
}

// --- Llamadas a la API -------------------------------------------------------------------------------------------

export const inventoryApi = {
  /** `GET /inventory/products`: todos los SKUs con `current_stock` y `stock_by_warehouse`, ordenados por `id`. */
  async listProducts(signal?: AbortSignal): Promise<Product[]> {
    return expectList(await http.get<unknown>("/inventory/products", signal, OPTIONS), isProduct);
  },

  /** `GET /inventory/products/{id}`: un SKU con su stock actual (404 si no existe). */
  async getProduct(id: number, signal?: AbortSignal): Promise<Product> {
    return expectItem(await http.get<unknown>(`/inventory/products/${id}`, signal, OPTIONS), isProduct);
  },

  /** `POST /inventory/orders/inbound`: recepción de mercancía. El `user_uuid` lo pone la API a partir del token. */
  async createInbound(payload: StockEntryPayload): Promise<StockEntry> {
    return expectItem(await http.post<unknown>("/inventory/orders/inbound", payload, OPTIONS), isStockEntry);
  },

  /** `POST /inventory/orders/outbound`: despacho o pérdida. 400 si deja el stock del almacén por debajo de cero. */
  async createOutbound(payload: StockExitPayload): Promise<StockExit> {
    return expectItem(await http.post<unknown>("/inventory/orders/outbound", payload, OPTIONS), isStockExit);
  },

  /** `GET /inventory/orders`: entradas y salidas con los datos de su SKU, de la más reciente a la más antigua. */
  async listOrders(filters: MovementFilters, signal?: AbortSignal): Promise<Movement[]> {
    const params = new URLSearchParams();
    if (filters.warehouse) params.set("warehouse", filters.warehouse);
    if (filters.sku_id) params.set("sku_id", filters.sku_id);
    const query = params.toString();
    return expectList(await http.get<unknown>(`/inventory/orders${query ? `?${query}` : ""}`, signal, OPTIONS), isMovement);
  },
};

export const NO_MOVEMENT_FILTERS: MovementFilters = { warehouse: "", sku_id: "" };

// --- Indicadores de stock ----------------------------------------------------------------------------------------

/**
 * Umbrales de PRESENTACIÓN del stock, no reglas de negocio: CONTEXT-gestor-inventario.es.md no define un stock mínimo
 * por SKU. Se han elegido a partir de los datos semilla (entradas de 20 a 120 unidades por recepción) para que una
 * recepción típica saque al SKU del aviso. Cámbialos aquí si negocio fija mínimos reales.
 *
 * - `out` (agotado): 0 unidades o menos.
 * - `critical` (crítico): de 1 a `critical` unidades.
 * - `low` (bajo): de `critical + 1` a `low` unidades.
 * - `healthy` (saludable): más de `low` unidades.
 */
export const STOCK_THRESHOLDS = { critical: 10, low: 30 } as const;

export type StockLevel = "out" | "critical" | "low" | "healthy";

export function stockLevel(stock: number): StockLevel {
  if (stock <= 0) return "out";
  if (stock <= STOCK_THRESHOLDS.critical) return "critical";
  if (stock <= STOCK_THRESHOLDS.low) return "low";
  return "healthy";
}

export const STOCK_LEVEL_LABELS: Record<StockLevel, string> = {
  out: "Agotado",
  critical: "Stock crítico",
  low: "Stock bajo",
  healthy: "Stock saludable",
};

// --- Formularios -------------------------------------------------------------------------------------------------

/** Mismos límites que la API (`inventory_schemas.py`). */
export const MAX_QUANTITY = 2_147_483_647;
export const REFERENCE_MAX_LENGTH = 64;
export const TRACKING_MAX_LENGTH = 64;

/** Entero positivo escrito por el usuario («12»), o `null` si no lo es. La API rechaza `"5"`, `5.0` y `true`. */
export function parseQuantity(text: string): number | null {
  const value = text.trim();
  if (!/^\d+$/.test(value)) return null;
  const quantity = Number(value);
  return quantity > 0 && quantity <= MAX_QUANTITY ? quantity : null;
}

/** «Zapatilla blanca clásica - Talla 42 · CLT-SNK-W-42 · Los Ángeles (LA)»: el nombre se repite entre almacenes. */
export function productOptionLabel(product: Pick<Product, "name" | "sku" | "warehouse">): string {
  return `${product.name} · ${product.sku} · ${warehouseLabel(product.warehouse)}`;
}

/** Identificador del producto elegido en el selector (`""` = ninguno). Viene de `?sku_id=` o del propio selector. */
export function parseSkuId(value: string | null | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const id = Number(value);
  return id > 0 && Number.isSafeInteger(id) ? id : null;
}

const MESSAGES = {
  sku: "Elige un producto.",
  quantityRequired: "La cantidad es obligatoria.",
  quantityInvalid: "La cantidad debe ser un número entero mayor que 0.",
  quantityTooLarge: `La cantidad no puede superar ${MAX_QUANTITY.toLocaleString("es-ES")}.`,
  referenceRequired: "La referencia es obligatoria.",
  referenceTooLong: `La referencia no puede superar los ${REFERENCE_MAX_LENGTH} caracteres.`,
  exitType: "Elige el tipo de salida.",
  trackingRequired: "El número de seguimiento es obligatorio en un despacho.",
  trackingTooLong: `El número de seguimiento no puede superar los ${TRACKING_MAX_LENGTH} caracteres.`,
  trackingForbidden: "Una pérdida no lleva número de seguimiento.",
} as const;

export function exceedsStockMessage(available: number): string {
  return `La cantidad supera el stock disponible (${available.toLocaleString("es-ES")} ${available === 1 ? "unidad" : "unidades"}).`;
}

function quantityError(text: string): string | null {
  if (!text.trim()) return MESSAGES.quantityRequired;
  if (parseQuantity(text) !== null) return null;
  return /^\s*\d+\s*$/.test(text) && Number(text) > MAX_QUANTITY ? MESSAGES.quantityTooLarge : MESSAGES.quantityInvalid;
}

export interface InboundDraft {
  skuId: string;
  quantity: string;
  reference: string;
}

export const EMPTY_INBOUND_DRAFT: InboundDraft = { skuId: "", quantity: "", reference: "" };

/** Campos del formulario de entrada en orden de aparición. Coinciden con los de la API para mostrar sus errores. */
export const INBOUND_FIELDS = ["sku_id", "quantity", "reference"] as const;
export type InboundField = (typeof INBOUND_FIELDS)[number];

export function validateInboundDraft(draft: InboundDraft): {
  payload: StockEntryPayload | null;
  errors: Partial<Record<InboundField, string>>;
} {
  const errors: Partial<Record<InboundField, string>> = {};
  const skuId = parseSkuId(draft.skuId);
  const quantity = parseQuantity(draft.quantity);
  const reference = draft.reference.trim();

  if (skuId === null) errors.sku_id = MESSAGES.sku;
  const quantityMessage = quantityError(draft.quantity);
  if (quantityMessage) errors.quantity = quantityMessage;
  if (!reference) errors.reference = MESSAGES.referenceRequired;
  else if (reference.length > REFERENCE_MAX_LENGTH) errors.reference = MESSAGES.referenceTooLong;

  if (Object.keys(errors).length > 0 || skuId === null || quantity === null) return { payload: null, errors };
  // Sin `warehouse`: la API registra la entrada en el almacén del SKU, que es el que muestra el formulario.
  return { payload: { sku_id: skuId, quantity, reference }, errors };
}

export interface OutboundDraft {
  skuId: string;
  quantity: string;
  exitType: ExitType | "";
  trackingNumber: string;
}

export const EMPTY_OUTBOUND_DRAFT: OutboundDraft = { skuId: "", quantity: "", exitType: "", trackingNumber: "" };

export const OUTBOUND_FIELDS = ["sku_id", "exit_type", "tracking_number", "quantity"] as const;
export type OutboundField = (typeof OUTBOUND_FIELDS)[number];

/**
 * `available` es el stock del producto elegido tal como lo acaba de devolver la API, o `null` si todavía no se conoce
 * (cargando o error): sin un dato fiable no se bloquea el envío por stock y decide la API (400).
 */
export function validateOutboundDraft(
  draft: OutboundDraft,
  available: number | null
): { payload: StockExitPayload | null; errors: Partial<Record<OutboundField, string>> } {
  const errors: Partial<Record<OutboundField, string>> = {};
  const skuId = parseSkuId(draft.skuId);
  const quantity = parseQuantity(draft.quantity);
  const tracking = draft.trackingNumber.trim();

  if (skuId === null) errors.sku_id = MESSAGES.sku;
  if (!draft.exitType) errors.exit_type = MESSAGES.exitType;
  if (draft.exitType === "dispatch") {
    if (!tracking) errors.tracking_number = MESSAGES.trackingRequired;
    else if (tracking.length > TRACKING_MAX_LENGTH) errors.tracking_number = MESSAGES.trackingTooLong;
  }
  const quantityMessage = quantityError(draft.quantity);
  if (quantityMessage) errors.quantity = quantityMessage;
  else if (quantity !== null && available !== null && quantity > available) {
    errors.quantity = exceedsStockMessage(available);
  }

  if (Object.keys(errors).length > 0 || skuId === null || quantity === null || !draft.exitType) {
    return { payload: null, errors };
  }
  return {
    errors,
    payload: {
      sku_id: skuId,
      quantity,
      exit_type: draft.exitType,
      // Regla 3: obligatorio en un despacho y nulo en una pérdida (lo que hubiera escrito antes se descarta).
      tracking_number: draft.exitType === "dispatch" ? tracking : null,
    },
  };
}

// --- Errores de la API -------------------------------------------------------------------------------------------

/** Mensaje literal de la regla 2 del briefing, que la API devuelve en inglés con un 400. */
const INSUFFICIENT_STOCK = /^Insufficient stock for SKU '(.+)'\. Available: (-?\d+), requested: (\d+)\.$/;

export interface InsufficientStock {
  sku: string;
  available: number;
  requested: number;
}

export function parseInsufficientStock(error: unknown): InsufficientStock | null {
  if (!(error instanceof ApiError) || error.status !== 400) return null;
  const match = error.message.match(INSUFFICIENT_STOCK);
  if (!match) return null;
  return { sku: match[1], available: Number(match[2]), requested: Number(match[3]) };
}

export function insufficientStockMessage({ sku, available, requested }: InsufficientStock): string {
  const units = (n: number) => `${n.toLocaleString("es-ES")} ${n === 1 ? "unidad" : "unidades"}`;
  return `Stock insuficiente para el SKU ${sku}: hay ${units(available)} disponibles y has pedido ${units(requested)}.`;
}

/** Mensajes de validación propios de la API (`inventory_schemas.py`), redactados para quien usa el formulario. */
const API_FIELD_MESSAGES: Record<string, string> = {
  "tracking_number es obligatorio cuando exit_type es 'dispatch'": MESSAGES.trackingRequired,
  "tracking_number debe ser nulo cuando exit_type es 'loss'": MESSAGES.trackingForbidden,
};

/**
 * Errores por campo de una respuesta de la API, con las claves de la API (`quantity`, `tracking_number`…). El 400 de
 * stock insuficiente va al campo `quantity`; los 422 traen ya su campo (`lib/http.ts` traduce los de Pydantic).
 */
export function inventoryFieldErrors(error: unknown): Record<string, string> {
  const insufficient = parseInsufficientStock(error);
  if (insufficient) return { quantity: insufficientStockMessage(insufficient) };
  if (!(error instanceof ApiError) || (error.status !== 400 && error.status !== 422)) return {};
  return Object.fromEntries(
    Object.entries(error.fieldErrors).map(([field, message]) => [field, API_FIELD_MESSAGES[message] ?? message])
  );
}

/**
 * Mensaje general para cualquier error del inventario. `action` completa la frase («No se ha podido cargar los
 * productos…»). Nunca muestra JSON, trazas ni el texto en inglés de la API.
 */
export function inventoryErrorMessage(error: unknown, action: string): string {
  const insufficient = parseInsufficientStock(error);
  if (insufficient) return insufficientStockMessage(insufficient);
  if (error instanceof ApiError) {
    if ((error.status === 400 || error.status === 422) && Object.keys(error.fieldErrors).length > 0) {
      return "Revisa los campos marcados y vuelve a intentarlo.";
    }
    if (error.status === 404) return "El producto ya no existe en el inventario. Actualiza el listado de productos.";
  }
  return apiErrorMessage(error, action);
}

// --- Formato -----------------------------------------------------------------------------------------------------

const QUANTITY_FORMAT = new Intl.NumberFormat("es-ES");

export function formatQuantity(n: number): string {
  return QUANTITY_FORMAT.format(n);
}

/** Fecha y hora en español y en la zona horaria del navegador (mismo formato que el gestor de incidencias). */
export function formatMovementDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" }).format(date);
}
