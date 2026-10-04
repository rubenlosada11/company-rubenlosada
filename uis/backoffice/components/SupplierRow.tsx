"use client";

import { useState } from "react";
import { categoryLabel, countryLabel, statusLabel } from "@/lib/data/suppliers";
import { ApiError, apiErrorMessage } from "@/lib/http";
import { formatDateTime, formatRate, parseRate, suppliersApi } from "@/lib/suppliers";
import type { Supplier } from "@/types";
import { Badge } from "./Badge";

const buttonBase =
  "inline-flex items-center justify-center rounded-full px-3 py-1.5 text-xs font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-60";

/** Error de una edición en la fila: el de su campo si la API lo rechaza por validación; si no, el mensaje general. */
function errorMessage(error: unknown, field: string, action: string): string {
  return (error instanceof ApiError && error.fieldErrors[field]) || apiErrorMessage(error, action);
}

interface SupplierRowProps {
  supplier: Supplier;
  onUpdated: (supplier: Supplier) => void;
}

export function SupplierRow({ supplier, onUpdated }: SupplierRowProps) {
  const [editingRate, setEditingRate] = useState(false);
  const [rateInput, setRateInput] = useState("");
  const [savingRate, setSavingRate] = useState(false);
  const [rateError, setRateError] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const isActive = supplier.status === "active";
  const rateInputId = `rate-${supplier.id}`;

  function startEditing() {
    setRateInput(String(supplier.rate_per_shipment));
    setRateError(null);
    setEditingRate(true);
  }

  async function saveRate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rate = parseRate(rateInput);
    if (rate === null) {
      setRateError("La tarifa debe ser un número mayor que 0.");
      return;
    }
    setSavingRate(true);
    setRateError(null);
    try {
      onUpdated(await suppliersApi.updateRate(supplier.id, rate));
      setEditingRate(false);
    } catch (error) {
      setRateError(errorMessage(error, "rate_per_shipment", "guardar la tarifa"));
    } finally {
      setSavingRate(false);
    }
  }

  async function toggleStatus() {
    setSavingStatus(true);
    setStatusError(null);
    try {
      onUpdated(await suppliersApi.updateStatus(supplier.id, isActive ? "suspended" : "active"));
    } catch (error) {
      setStatusError(errorMessage(error, "status", "cambiar el estado"));
    } finally {
      setSavingStatus(false);
    }
  }

  return (
    <tr data-supplier-id={supplier.id} className={`align-top ${isActive ? "" : "bg-amber-50/40"}`}>
      <td className="px-4 py-4">
        <p className="font-semibold text-slate-900">{supplier.name}</p>
        {supplier.service_zone ? <p className="text-xs text-slate-600">{supplier.service_zone}</p> : null}
        {supplier.contact_email ? (
          <a
            href={`mailto:${supplier.contact_email}`}
            className="text-xs font-semibold text-blue-700 underline-offset-2 hover:underline"
          >
            {supplier.contact_email}
          </a>
        ) : null}
        {supplier.notes ? <p className="mt-1 max-w-xs text-xs text-slate-500">{supplier.notes}</p> : null}
      </td>

      <td className="px-4 py-4 text-sm whitespace-nowrap text-slate-700">{countryLabel(supplier.country)}</td>

      <td className="px-4 py-4">
        <ul className="flex max-w-56 flex-wrap gap-1.5" aria-label="Categorías">
          {supplier.categories.map((category) => (
            <li key={category}>
              <Badge tone="blue">{categoryLabel(category)}</Badge>
            </li>
          ))}
        </ul>
      </td>

      <td className="px-4 py-4">
        {editingRate ? (
          <form onSubmit={saveRate} noValidate className="flex min-w-44 flex-col gap-2" aria-busy={savingRate}>
            <label htmlFor={rateInputId} className="sr-only">
              Nueva tarifa de {supplier.name} en {supplier.currency}
            </label>
            <div className="flex items-center gap-1.5">
              <input
                id={rateInputId}
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={rateInput}
                onChange={(event) => setRateInput(event.target.value)}
                disabled={savingRate}
                aria-invalid={rateError ? true : undefined}
                aria-describedby={rateError ? `${rateInputId}-error` : undefined}
                autoFocus
                className="w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none"
              />
              <span className="text-xs font-semibold text-slate-500">{supplier.currency}</span>
            </div>
            <div className="flex gap-1.5">
              <button type="submit" disabled={savingRate} className={`${buttonBase} bg-blue-700 text-white hover:bg-blue-800`}>
                {savingRate ? "Guardando…" : "Guardar"}
              </button>
              <button
                type="button"
                onClick={() => setEditingRate(false)}
                disabled={savingRate}
                className={`${buttonBase} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`}
              >
                Cancelar
              </button>
            </div>
            {rateError ? (
              <p id={`${rateInputId}-error`} role="alert" className="text-xs font-semibold text-red-700">
                {rateError}
              </p>
            ) : null}
          </form>
        ) : (
          <div className="flex flex-col items-start gap-1.5">
            <span className="font-heading text-base whitespace-nowrap text-slate-900">{formatRate(supplier)}</span>
            <button
              type="button"
              onClick={startEditing}
              aria-label={`Editar tarifa de ${supplier.name}`}
              className={`${buttonBase} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`}
            >
              Editar tarifa
            </button>
          </div>
        )}
      </td>

      <td className="px-4 py-4">
        <div className="flex flex-col items-start gap-1.5">
          <Badge tone={isActive ? "emerald" : "amber"}>{statusLabel(supplier.status)}</Badge>
          <button
            type="button"
            onClick={toggleStatus}
            disabled={savingStatus}
            aria-label={`${isActive ? "Suspender" : "Reactivar"} a ${supplier.name}`}
            className={`${buttonBase} ${
              isActive
                ? "border border-amber-300 bg-white text-amber-900 hover:bg-amber-50"
                : "border border-emerald-300 bg-white text-emerald-900 hover:bg-emerald-50"
            }`}
          >
            {savingStatus ? "Guardando…" : isActive ? "Suspender" : "Reactivar"}
          </button>
          {statusError ? (
            <p role="alert" className="max-w-40 text-xs font-semibold text-red-700">
              {statusError}
            </p>
          ) : null}
        </div>
      </td>

      <td className="px-4 py-4 text-xs whitespace-nowrap text-slate-600">
        <time dateTime={supplier.updated_at}>{formatDateTime(supplier.updated_at)}</time>
      </td>
    </tr>
  );
}
