// Inventario unificado (`/inventory` en services/api, Hito 5). Campos y valores de CONTEXT-gestor-inventario.es.md,
// contrastados con los schemas reales de la API (`services/api/app/inventory_schemas.py`).

export type Warehouse = "LA" | "ZGZ";

export type Category = "fashion" | "electronics" | "cosmetics";

/** `dispatch`: envío a cliente (exige `tracking_number`). `loss`: discrepancia o daño confirmado (sin él). */
export type ExitType = "dispatch" | "loss";

/** Stock de un SKU en cada almacén por separado: la API nunca los suma (regla 6). */
export type StockByWarehouse = Record<Warehouse, number>;

/** `SKURead`: respuesta de `GET /inventory/products` y `GET /inventory/products/{id}`. */
export interface Product {
  id: number;
  name: string;
  /** Código asignado por la marca cliente, p. ej. `CLT-SNK-W-42`. */
  sku: string;
  client_name: string;
  category: Category;
  /** Almacén en el que está registrado el SKU. */
  warehouse: Warehouse;
  /** Calculado por la API: entradas − salidas en el almacén del SKU. */
  current_stock: number;
  stock_by_warehouse: StockByWarehouse;
}

/**
 * Cuerpo de `POST /inventory/orders/inbound`. `warehouse` es opcional: sin él, la API usa el almacén del SKU. `id`,
 * `created_at` y `user_uuid` los pone el servidor (`user_uuid` sale del token).
 */
export interface StockEntryPayload {
  sku_id: number;
  quantity: number;
  /** Referencia de despacho del cliente, p. ej. el número de orden de compra. */
  reference: string;
  warehouse?: Warehouse;
}

/** Cuerpo de `POST /inventory/orders/outbound`. `tracking_number` obligatorio en `dispatch` y nulo en `loss`. */
export interface StockExitPayload {
  sku_id: number;
  quantity: number;
  exit_type: ExitType;
  tracking_number: string | null;
  warehouse?: Warehouse;
}

/** `StockEntryRead`: respuesta 201 de `POST /inventory/orders/inbound`. */
export interface StockEntry {
  id: number;
  sku_id: number;
  quantity: number;
  reference: string;
  warehouse: Warehouse;
  /** ISO 8601 en UTC (`…Z`). */
  created_at: string;
  user_uuid: string;
}

/** `StockExitRead`: respuesta 201 de `POST /inventory/orders/outbound`. */
export interface StockExit {
  id: number;
  sku_id: number;
  quantity: number;
  exit_type: ExitType;
  tracking_number: string | null;
  warehouse: Warehouse;
  created_at: string;
  user_uuid: string;
}

/** Datos del SKU que la API incluye en cada movimiento del historial (`SKUSummary`). */
export type ProductSummary = Omit<Product, "current_stock" | "stock_by_warehouse">;

export interface InboundMovement extends StockEntry {
  movement_type: "inbound";
  sku: ProductSummary;
}

export interface OutboundMovement extends StockExit {
  movement_type: "outbound";
  sku: ProductSummary;
}

/**
 * Elemento de `GET /inventory/orders`, de más reciente a más antiguo. Entradas y salidas tienen numeración propia: el
 * `id` solo es único junto con `movement_type`.
 */
export type Movement = InboundMovement | OutboundMovement;

/** Filtros de `GET /inventory/orders`; cadena vacía = sin filtrar por ese campo. */
export interface MovementFilters {
  warehouse: Warehouse | "";
  sku_id: string;
}
