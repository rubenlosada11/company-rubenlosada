"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatCard } from "@/components/StatCard";
import { categoryLabel, warehouseLabel } from "@/lib/data/inventory";
import {
  formatQuantity,
  inventoryApi,
  inventoryErrorMessage,
  STOCK_THRESHOLDS,
  stockLevel,
} from "@/lib/inventory";
import type { Product, Warehouse } from "@/types/inventory";
import { StockBadge } from "./StockBadge";

const actionClasses =
  "inline-flex min-h-10 items-center justify-center rounded-full px-4 text-sm font-bold whitespace-nowrap transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

interface ListResult {
  /** Carga a la que corresponde el resultado: si no coincide con la actual, se está actualizando. */
  key: number;
  products: Product[];
  error: string | null;
}

/** Stock del SKU en el otro almacén, si lo tiene (regla 6: se muestra aparte, nunca sumado a `current_stock`). */
function otherWarehouse(product: Product): { warehouse: Warehouse; stock: number } | null {
  const warehouse: Warehouse = product.warehouse === "LA" ? "ZGZ" : "LA";
  const stock = product.stock_by_warehouse[warehouse];
  return stock !== 0 ? { warehouse, stock } : null;
}

export function ProductList() {
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);

  const loading = result?.key !== reloadKey;
  const products = result?.products ?? [];

  // Datos siempre de la API: cada visita a la página (y cada «Actualizar») vuelve a pedir el stock calculado.
  useEffect(() => {
    const controller = new AbortController();
    inventoryApi
      .listProducts(controller.signal)
      .then((list) => setResult({ key: reloadKey, products: list, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // Se conserva lo que ya se mostraba: un fallo al actualizar no vacía la tabla.
        setResult((current) => ({
          key: reloadKey,
          products: current?.products ?? [],
          error: inventoryErrorMessage(error, "cargar los productos"),
        }));
      });
    return () => controller.abort();
  }, [reloadKey]);

  const counts = { healthy: 0, low: 0, alert: 0 };
  for (const product of products) {
    const level = stockLevel(product.current_stock);
    if (level === "healthy") counts.healthy += 1;
    else if (level === "low") counts.low += 1;
    else counts.alert += 1;
  }

  const firstLoad = result === null;
  const reload = () => setReloadKey((key) => key + 1);

  return (
    <div className="space-y-6">
      {!firstLoad && products.length > 0 ? (
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="SKUs en el inventario" value={products.length} detail="Los Ángeles y Zaragoza" />
          <StatCard label="Stock saludable" value={counts.healthy} detail={`Más de ${STOCK_THRESHOLDS.low} unidades`} />
          <StatCard
            label="Stock bajo"
            value={counts.low}
            detail={`De ${STOCK_THRESHOLDS.critical + 1} a ${STOCK_THRESHOLDS.low} unidades`}
          />
          <StatCard
            label="Crítico o agotado"
            value={counts.alert}
            detail={`${STOCK_THRESHOLDS.critical} unidades o menos`}
          />
        </dl>
      ) : null}

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center">
        <p role="status" className="text-sm font-semibold text-slate-600">
          {loading
            ? firstLoad
              ? "Cargando productos…"
              : "Actualizando el stock…"
            : result?.error && products.length === 0
              ? "Sin datos"
              : `${products.length} ${products.length === 1 ? "producto" : "productos"}`}
        </p>
        <p className="text-xs text-slate-500 sm:ml-2">
          Indicadores orientativos de esta pantalla, no mínimos de negocio: crítico hasta {STOCK_THRESHOLDS.critical}{" "}
          unidades y bajo hasta {STOCK_THRESHOLDS.low}.
        </p>
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-60 sm:ml-auto"
        >
          Actualizar
        </button>
      </div>

      {result?.error && !loading ? (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p className="font-bold">
            {products.length > 0 ? "No se pudo actualizar el stock." : "No se pudieron cargar los productos."}
          </p>
          <p className="mt-1">{result.error}</p>
          {products.length > 0 ? (
            <p className="mt-1">La tabla muestra los últimos datos recibidos.</p>
          ) : null}
          <button
            type="button"
            onClick={reload}
            className="mt-3 min-h-11 rounded-full border border-red-300 bg-white px-5 text-sm font-bold text-red-800 transition hover:bg-red-100"
          >
            Reintentar
          </button>
        </div>
      ) : null}

      {result?.error && products.length === 0 && !loading ? null : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className={`w-full min-w-[880px] text-left ${loading && !firstLoad ? "opacity-60" : ""}`} aria-busy={loading}>
            <caption className="sr-only">Productos del inventario con su stock actual</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold tracking-wide text-slate-500 uppercase">
              <tr>
                <th scope="col" className="px-4 py-3">Producto</th>
                <th scope="col" className="px-4 py-3">Cliente</th>
                <th scope="col" className="px-4 py-3">Almacén</th>
                <th scope="col" className="px-4 py-3 text-right">Stock actual</th>
                <th scope="col" className="px-4 py-3">Nivel</th>
                <th scope="col" className="px-4 py-3">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.map((product) => {
                const other = otherWarehouse(product);
                return (
                  <tr key={product.id} data-product-id={product.id} className="align-top">
                    <td className="px-4 py-4">
                      <p className="font-semibold text-slate-900">{product.name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        <span className="font-mono">{product.sku}</span> · {categoryLabel(product.category)}
                      </p>
                    </td>
                    <td className="px-4 py-4 text-sm text-slate-700">{product.client_name}</td>
                    <td className="px-4 py-4 text-sm font-semibold whitespace-nowrap text-slate-700">
                      {warehouseLabel(product.warehouse)}
                    </td>
                    <td className="px-4 py-4 text-right">
                      <p className="font-heading text-2xl text-slate-900" data-current-stock>
                        {formatQuantity(product.current_stock)}
                      </p>
                      <p className="text-xs text-slate-500">unidades</p>
                      {other ? (
                        <p className="mt-1 text-xs text-slate-500">
                          Además, {formatQuantity(other.stock)} en {warehouseLabel(other.warehouse)}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-4">
                      <StockBadge stock={product.current_stock} />
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        <Link
                          href={`/inventory/orders/inbound?sku_id=${product.id}`}
                          aria-label={`Registrar entrada de ${product.name} (${product.sku})`}
                          className={`${actionClasses} bg-blue-700 text-white hover:bg-blue-800`}
                        >
                          Registrar entrada
                        </Link>
                        <Link
                          href={`/inventory/orders/outbound?sku_id=${product.id}`}
                          aria-label={`Registrar salida de ${product.name} (${product.sku})`}
                          className={`${actionClasses} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`}
                        >
                          Registrar salida
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {firstLoad ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-600">
                    Cargando productos…
                  </td>
                </tr>
              ) : null}
              {!loading && !result?.error && products.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-600">
                    Todavía no hay productos en el inventario. Cuando se registren SKUs en la API aparecerán aquí con
                    su stock.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
