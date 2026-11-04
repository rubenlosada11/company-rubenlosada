"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { warehouseLabel } from "@/lib/data/inventory";
import { formatQuantity, inventoryApi, inventoryErrorMessage, productOptionLabel } from "@/lib/inventory";
import { useApiRequest } from "@/lib/useApiRequest";
import type { Product } from "@/types/inventory";
import { StockBadge } from "./StockBadge";

// Mismo estilo que el formulario de incidencias: controles de 48 px y texto de 16 px (terminales táctiles del almacén).
export const inputClasses =
  "min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 shadow-sm transition focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none aria-invalid:border-red-500 aria-invalid:bg-red-50 disabled:bg-slate-100";
export const labelClasses = "text-sm font-bold text-slate-700";
export const submitClasses =
  "min-h-12 w-full rounded-full bg-blue-700 px-8 py-3 text-base font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto";

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-sm font-semibold text-red-700">
      {message}
    </p>
  );
}

// Lista vacía estable: con `data ?? []` sería un array nuevo en cada render y el `useMemo` del selector se rehace siempre.
const NO_PRODUCTS: Product[] = [];

interface ProductsState {
  products: Product[];
  loading: boolean;
  error: string | null;
  /** Ya ha terminado alguna carga (`false` solo la primera vez). */
  settled: boolean;
  reload: () => void;
}

/**
 * Productos de `GET /inventory/products`: el listado del inventario y los selectores de producto. Si una recarga
 * falla, se conservan los últimos productos recibidos.
 */
export function useProducts(): ProductsState {
  const { data, loading, error, settled, reload } = useApiRequest(
    "products",
    (signal) => inventoryApi.listProducts(signal),
    (reason) => inventoryErrorMessage(reason, "cargar los productos"),
    { keepDataOnError: true }
  );
  return { products: data ?? NO_PRODUCTS, loading, error, settled, reload };
}

export type StockState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; product: Product }
  | { status: "error"; message: string };

/**
 * Stock actual del producto elegido, pedido a la API (`GET /inventory/products/{id}`) cada vez que cambia la selección
 * o se llama a `refresh`.
 *
 * Cambios rápidos de producto: cada consulta se cancela al cambiar la selección y su resultado se guarda junto a la
 * consulta que lo pidió (`skuId` + `version`). Lo que no corresponde a la consulta actual se trata como «cargando»:
 * nunca se muestra el stock del producto anterior ni una respuesta antigua pisa a la nueva.
 */
export function useProductStock(skuId: number | null): { stock: StockState; refresh: () => void } {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ skuId: number; version: number; state: StockState } | null>(null);

  useEffect(() => {
    if (skuId === null) return;
    const controller = new AbortController();
    inventoryApi
      .getProduct(skuId, controller.signal)
      .then((product) => setResult({ skuId, version, state: { status: "ready", product } }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({
          skuId,
          version,
          state: { status: "error", message: inventoryErrorMessage(error, "consultar el stock") },
        });
      });
    return () => controller.abort();
  }, [skuId, version]);

  const refresh = useCallback(() => setVersion((n) => n + 1), []);

  let stock: StockState = { status: "idle" };
  if (skuId !== null) {
    stock = result && result.skuId === skuId && result.version === version ? result.state : { status: "loading" };
  }
  return { stock, refresh };
}

interface ProductSelectProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  products: ProductsState;
  error?: string;
  errorId: string;
  disabled?: boolean;
}

/** Selector de producto por nombre (con código y almacén: el mismo nombre existe en LA y en ZGZ). */
export function ProductSelect({ id, value, onChange, products, error, errorId, disabled }: ProductSelectProps) {
  const unavailable = products.error !== null && products.products.length === 0;
  // Los formularios de entrada y salida se vuelven a renderizar con cada pulsación (cantidad, referencia, número de
  // seguimiento). Las opciones solo dependen de la lista de productos: se construyen una vez por lista recibida y, al
  // ser los mismos elementos, React no vuelve a comparar las `<option>` (cientos en un almacén real).
  const options = useMemo(
    () =>
      products.products.map((product) => (
        <option key={product.id} value={String(product.id)}>
          {productOptionLabel(product)}
        </option>
      )),
    [products.products]
  );
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className={labelClasses}>
        Producto
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || (products.loading && products.products.length === 0) || unavailable}
        required
        aria-invalid={error ? true : undefined}
        aria-describedby={[error ? errorId : null, `${id}-hint`].filter(Boolean).join(" ")}
        className={inputClasses}
      >
        <option value="">
          {products.loading && products.products.length === 0 ? "Cargando productos…" : "Elige un producto"}
        </option>
        {options}
      </select>
      <FieldError id={errorId} message={error} />
      {products.error ? (
        <div id={`${id}-hint`} role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-800">
          <span className="font-semibold">{products.error}</span>
          <button
            type="button"
            onClick={products.reload}
            className="min-h-10 rounded-full border border-red-300 bg-white px-4 text-sm font-bold text-red-800 transition hover:bg-red-100"
          >
            Reintentar
          </button>
        </div>
      ) : (
        <p id={`${id}-hint`} className="text-sm text-slate-600">
          {!products.loading && products.products.length === 0
            ? "No hay productos en el inventario todavía."
            : "Nombre del producto, código SKU del cliente y almacén en el que está registrado."}
        </p>
      )}
    </div>
  );
}

/** Ficha del producto elegido con su stock actual tal como lo acaba de calcular la API. */
export function StockPanel({ stock, id }: { stock: StockState; id: string }) {
  if (stock.status === "idle") return null;
  return (
    <div
      id={id}
      aria-live="polite"
      data-stock-status={stock.status}
      className="rounded-xl border border-slate-200 bg-slate-50 p-4"
    >
      {stock.status === "loading" ? (
        <p className="text-sm font-semibold text-slate-600">Consultando el stock actual…</p>
      ) : stock.status === "error" ? (
        <p className="text-sm font-semibold text-red-800">{stock.message}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <p className="text-xs font-bold tracking-wide text-slate-500 uppercase">
              Stock actual en {warehouseLabel(stock.product.warehouse)}
            </p>
            <p className="font-heading text-3xl text-slate-900" data-panel-stock={stock.product.current_stock}>
              {formatQuantity(stock.product.current_stock)}{" "}
              <span className="font-body text-base text-slate-600">
                {stock.product.current_stock === 1 ? "unidad" : "unidades"}
              </span>
            </p>
          </div>
          <StockBadge stock={stock.product.current_stock} />
          <p className="text-sm text-slate-600">
            {stock.product.client_name} · <span className="font-mono">{stock.product.sku}</span>
          </p>
        </div>
      )}
    </div>
  );
}
