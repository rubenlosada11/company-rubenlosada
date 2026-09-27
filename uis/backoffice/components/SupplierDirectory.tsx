"use client";

import { useEffect, useState } from "react";
import { SUPPLIER_CATEGORIES, SUPPLIER_COUNTRIES } from "@/lib/data/suppliers";
import { ApiError } from "@/lib/http";
import { suppliersApi } from "@/lib/suppliers";
import type { Supplier, SupplierFilters } from "@/types";
import { SupplierForm } from "./SupplierForm";
import { SupplierRow } from "./SupplierRow";

const selectClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto";

const NO_FILTERS: SupplierFilters = { country: "", category: "" };

interface ListResult {
  /** Petición (filtros + recarga) a la que corresponde el resultado: si no coincide con la actual, está cargando. */
  key: string;
  suppliers: Supplier[];
  error: string | null;
}

function matchesFilters(supplier: Supplier, filters: SupplierFilters): boolean {
  return (
    (!filters.country || supplier.country === filters.country) &&
    (!filters.category || supplier.categories.includes(filters.category))
  );
}

export function SupplierDirectory() {
  const [filters, setFilters] = useState<SupplierFilters>(NO_FILTERS);
  const [reloadToken, setReloadToken] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const requestKey = `${filters.country}|${filters.category}|${reloadToken}`;
  const loading = result?.key !== requestKey;
  const suppliers = result?.suppliers ?? [];
  const activeCount = suppliers.filter((supplier) => supplier.status === "active").length;
  const hasFilters = Boolean(filters.country || filters.category);

  // Cada cambio de filtro pide los datos a la API (GET /suppliers?country=…&category=…), sin recargar la página.
  useEffect(() => {
    const controller = new AbortController();
    suppliersApi
      .list(filters, controller.signal)
      .then((list) => setResult({ key: requestKey, suppliers: list, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : "Error inesperado al cargar los proveedores.";
        setResult({ key: requestKey, suppliers: [], error: message });
      });
    return () => controller.abort();
  }, [filters, requestKey]);

  function handleUpdated(updated: Supplier) {
    setResult((current) =>
      current
        ? { ...current, suppliers: current.suppliers.map((item) => (item.id === updated.id ? updated : item)) }
        : current
    );
  }

  function handleCreated(created: Supplier) {
    setShowForm(false);
    setNotice(
      `«${created.name}» registrado con el id ${created.id}.` +
        (matchesFilters(created, filters) ? "" : " No aparece en la lista porque no coincide con los filtros aplicados.")
    );
    setReloadToken((token) => token + 1);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="filter-country" className="text-xs font-bold tracking-wide text-slate-500 uppercase">
            País
          </label>
          <select
            id="filter-country"
            value={filters.country}
            onChange={(event) =>
              setFilters((current) => ({ ...current, country: event.target.value as SupplierFilters["country"] }))
            }
            className={selectClasses}
          >
            <option value="">Todos los países</option>
            {SUPPLIER_COUNTRIES.map((country) => (
              <option key={country.value} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="filter-category" className="text-xs font-bold tracking-wide text-slate-500 uppercase">
            Categoría
          </label>
          <select
            id="filter-category"
            value={filters.category}
            onChange={(event) =>
              setFilters((current) => ({ ...current, category: event.target.value as SupplierFilters["category"] }))
            }
            className={selectClasses}
          >
            <option value="">Todas las categorías</option>
            {SUPPLIER_CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>
                {category.label}
              </option>
            ))}
          </select>
        </div>

        {hasFilters ? (
          <button
            type="button"
            onClick={() => setFilters(NO_FILTERS)}
            className="rounded-full border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
          >
            Quitar filtros
          </button>
        ) : null}

        <p role="status" className="text-sm font-semibold text-slate-600 sm:ml-auto">
          {loading
            ? "Cargando proveedores…"
            : result?.error
              ? "Sin datos"
              : `${suppliers.length} ${suppliers.length === 1 ? "proveedor" : "proveedores"} · ${activeCount} activos · ${suppliers.length - activeCount} suspendidos`}
        </p>

        <button
          type="button"
          onClick={() => {
            setNotice(null);
            setShowForm((open) => !open);
          }}
          aria-expanded={showForm}
          aria-controls="new-supplier-panel"
          className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          {showForm ? "Cerrar formulario" : "Nuevo proveedor"}
        </button>
      </div>

      {notice ? (
        <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-semibold text-emerald-900">
          {notice}
        </p>
      ) : null}

      {showForm ? (
        <div id="new-supplier-panel">
          <SupplierForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
        </div>
      ) : null}

      {result?.error && !loading ? (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p className="font-bold">No se pudieron cargar los proveedores.</p>
          <p className="mt-1">{result.error}</p>
          <button
            type="button"
            onClick={() => setReloadToken((token) => token + 1)}
            className="mt-3 rounded-full border border-red-300 bg-white px-4 py-2 text-sm font-bold text-red-800 transition hover:bg-red-100"
          >
            Reintentar
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className={`w-full min-w-[920px] text-left ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <caption className="sr-only">Directorio de proveedores de TrackFlow</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold tracking-wide text-slate-500 uppercase">
              <tr>
                <th scope="col" className="px-4 py-3">Proveedor</th>
                <th scope="col" className="px-4 py-3">País</th>
                <th scope="col" className="px-4 py-3">Categorías</th>
                <th scope="col" className="px-4 py-3">Tarifa por envío</th>
                <th scope="col" className="px-4 py-3">Estado</th>
                <th scope="col" className="px-4 py-3">Tarifa actualizada</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {suppliers.map((supplier) => (
                <SupplierRow key={supplier.id} supplier={supplier} onUpdated={handleUpdated} />
              ))}
              {!loading && suppliers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-600">
                    {hasFilters
                      ? "Ningún proveedor coincide con los filtros seleccionados."
                      : "Todavía no hay proveedores. Ejecuta el seeder (uv run seed) o registra uno nuevo."}
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
