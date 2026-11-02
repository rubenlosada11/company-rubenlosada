"use client";

import { useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/Badge";
import { exitTypeLabel, WAREHOUSES, warehouseLabel } from "@/lib/data/inventory";
import {
  formatMovementDate,
  formatQuantity,
  inventoryApi,
  inventoryErrorMessage,
  NO_MOVEMENT_FILTERS,
  productOptionLabel,
} from "@/lib/inventory";
import { useApiRequest } from "@/lib/useApiRequest";
import type { Movement, MovementFilters, Warehouse } from "@/types/inventory";
import { useProducts } from "./formParts";

const selectClasses =
  "min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto sm:max-w-sm";
const filterLabelClasses = "text-xs font-bold tracking-wide text-slate-500 uppercase";
const buttonClasses =
  "min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-60";

/** Entradas y salidas tienen numeración propia: la clave única es el tipo más el id. */
const movementKey = (movement: Movement) => `${movement.movement_type}-${movement.id}`;

/** Historial de solo lectura de `GET /inventory/orders` (la API no permite editar ni borrar movimientos). */
export function MovementHistory() {
  const { user } = useAuth();
  const products = useProducts();
  const [filters, setFilters] = useState<MovementFilters>(NO_MOVEMENT_FILTERS);

  // Cada cambio de filtro pide los datos a la API (`?warehouse=` y `?sku_id=` son filtros de la propia API).
  const history = useApiRequest(
    `${filters.warehouse}|${filters.sku_id}`,
    (signal) => inventoryApi.listOrders(filters, signal),
    (error) => inventoryErrorMessage(error, "cargar el historial")
  );
  const { loading, reload } = history;
  const movements = history.data ?? [];
  const hasFilters = Boolean(filters.warehouse || filters.sku_id);
  const inbound = movements.filter((movement) => movement.movement_type === "inbound").length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="movement-filter-warehouse" className={filterLabelClasses}>
            Almacén
          </label>
          <select
            id="movement-filter-warehouse"
            value={filters.warehouse}
            onChange={(event) =>
              setFilters((current) => ({ ...current, warehouse: event.target.value as Warehouse | "" }))
            }
            className={selectClasses}
          >
            <option value="">Los dos almacenes</option>
            {WAREHOUSES.map((warehouse) => (
              <option key={warehouse.value} value={warehouse.value}>
                {warehouseLabel(warehouse.value)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="movement-filter-product" className={filterLabelClasses}>
            Producto
          </label>
          <select
            id="movement-filter-product"
            value={filters.sku_id}
            onChange={(event) => setFilters((current) => ({ ...current, sku_id: event.target.value }))}
            className={selectClasses}
          >
            <option value="">{products.error ? "Todos (no se pudo cargar la lista)" : "Todos los productos"}</option>
            {products.products.map((product) => (
              <option key={product.id} value={String(product.id)}>
                {productOptionLabel(product)}
              </option>
            ))}
          </select>
        </div>

        {hasFilters ? (
          <button type="button" onClick={() => setFilters(NO_MOVEMENT_FILTERS)} className={buttonClasses}>
            Quitar filtros
          </button>
        ) : null}

        <button type="button" onClick={reload} disabled={loading} className={`${buttonClasses} sm:ml-auto`}>
          Actualizar
        </button>
      </div>

      <p role="status" className="text-sm font-semibold text-slate-600">
        {loading
          ? "Cargando movimientos…"
          : history.error
            ? "Sin datos"
            : `${movements.length} ${movements.length === 1 ? "movimiento" : "movimientos"} (${inbound} ${inbound === 1 ? "entrada" : "entradas"} y ${movements.length - inbound} ${movements.length - inbound === 1 ? "salida" : "salidas"})${hasFilters ? " con los filtros aplicados" : ""}, del más reciente al más antiguo`}
      </p>

      {history.error && !loading ? (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p className="font-bold">No se pudo cargar el historial.</p>
          <p className="mt-1">{history.error}</p>
          <button
            type="button"
            onClick={reload}
            className="mt-3 min-h-11 rounded-full border border-red-300 bg-white px-5 text-sm font-bold text-red-800 transition hover:bg-red-100"
          >
            Reintentar
          </button>
        </div>
      ) : (
        // `relative`: los textos `sr-only` (posición absoluta) de las celdas quedan dentro del desplazamiento de la tabla
        // y no ensanchan la página en móvil. `tabIndex`: la tabla no tiene nada enfocable, así que la propia región debe
        // poder recibir el foco para desplazarla con el teclado.
        <div
          role="region"
          aria-label="Historial de movimientos"
          tabIndex={0}
          className="relative overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <table className={`w-full min-w-[1040px] text-left ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <caption className="sr-only">Historial de movimientos de stock (solo lectura)</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold tracking-wide text-slate-500 uppercase">
              <tr>
                <th scope="col" className="px-4 py-3">Fecha</th>
                <th scope="col" className="px-4 py-3">Tipo</th>
                <th scope="col" className="px-4 py-3">Producto</th>
                <th scope="col" className="px-4 py-3 text-right">Cantidad</th>
                <th scope="col" className="px-4 py-3">Detalle</th>
                <th scope="col" className="px-4 py-3">Registrado por</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {movements.map((movement) => {
                const isInbound = movement.movement_type === "inbound";
                return (
                  <tr
                    key={movementKey(movement)}
                    data-movement={movementKey(movement)}
                    data-movement-type={movement.movement_type}
                    className={`align-top border-l-4 ${isInbound ? "border-l-emerald-500" : "border-l-amber-500"}`}
                  >
                    <td className="px-4 py-4 text-sm whitespace-nowrap text-slate-700">
                      <time dateTime={movement.created_at}>{formatMovementDate(movement.created_at)}</time>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-col items-start gap-1.5">
                        <Badge tone={isInbound ? "emerald" : "amber"}>
                          <span aria-hidden="true" className="mr-1">
                            {isInbound ? "↓" : "↑"}
                          </span>
                          {isInbound ? "Entrada" : "Salida"}
                        </Badge>
                        {movement.movement_type === "outbound" ? (
                          <span className="text-xs font-semibold text-slate-600">
                            {exitTypeLabel(movement.exit_type)}
                          </span>
                        ) : (
                          <span className="text-xs font-semibold text-slate-600">Recepción</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <p className="font-semibold text-slate-900">{movement.sku.name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        <span className="font-mono">{movement.sku.sku}</span> · {warehouseLabel(movement.warehouse)}
                      </p>
                    </td>
                    <td className="px-4 py-4 text-right">
                      <p
                        className={`font-heading text-xl whitespace-nowrap ${isInbound ? "text-emerald-800" : "text-amber-800"}`}
                      >
                        <span aria-hidden="true">{isInbound ? "+" : "−"}</span>
                        {formatQuantity(movement.quantity)}
                        <span className="sr-only"> {isInbound ? "unidades recibidas" : "unidades retiradas"}</span>
                      </p>
                    </td>
                    <td className="px-4 py-4 text-sm text-slate-700">
                      {movement.movement_type === "inbound" ? (
                        <p>
                          Referencia: <span className="font-mono">{movement.reference}</span>
                        </p>
                      ) : movement.tracking_number ? (
                        <p>
                          Seguimiento: <span className="font-mono">{movement.tracking_number}</span>
                        </p>
                      ) : (
                        <p className="text-slate-500">Sin número de seguimiento</p>
                      )}
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-600">
                      <p className="max-w-56 font-mono break-all" data-user-uuid>
                        {movement.user_uuid}
                      </p>
                      {user && movement.user_uuid === user.id ? (
                        <p className="mt-1 font-sans font-semibold text-blue-800">Tú</p>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
              {loading && movements.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-600">
                    Cargando movimientos…
                  </td>
                </tr>
              ) : null}
              {!loading && movements.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-600">
                    {hasFilters
                      ? "Ningún movimiento coincide con los filtros seleccionados."
                      : "Todavía no hay movimientos de stock. Las entradas y salidas que se registren aparecerán aquí."}
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
