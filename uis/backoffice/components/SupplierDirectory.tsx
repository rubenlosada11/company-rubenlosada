"use client";

import { type ComponentProps, Suspense, use, useState } from "react";
import { SUPPLIER_CATEGORIES, SUPPLIER_COUNTRIES } from "@/lib/data/suppliers";
import { deferredModule } from "@/lib/deferredModule";
import { apiErrorMessage } from "@/lib/http";
import { suppliersApi } from "@/lib/suppliers";
import { useApiRequest } from "@/lib/useApiRequest";
import type { Supplier, SupplierFilters } from "@/types";
import { LoadErrorAlert } from "./LoadErrorAlert";
import type { SupplierForm as SupplierFormComponent } from "./SupplierForm";
import { SupplierRow } from "./SupplierRow";

// El formulario de alta solo aparece al pulsar «Nuevo proveedor»: su código (validación, campos, envío) va en un
// chunk aparte que se descarga entonces, no con la página. Se empieza a descargar en cuanto el puntero o el foco
// llegan al botón: al hacer clic normalmente ya está y se muestra sin pasar por el «Cargando…». Por qué
// `deferredModule` + `use()` y no `next/dynamic` ni `React.lazy`: ver `lib/deferredModule.ts`.
const loadSupplierForm = deferredModule(() => import("./SupplierForm").then((module) => module.SupplierForm));

function DeferredSupplierForm(props: ComponentProps<typeof SupplierFormComponent>) {
  const SupplierForm = use(loadSupplierForm());
  // `SupplierForm` es siempre la misma exportación del módulo (la promesa se guarda): no se crea en cada render.
  // eslint-disable-next-line react-hooks/static-components
  return <SupplierForm {...props} />;
}

function preloadSupplierForm() {
  // Solo adelanta la descarga. Si falla, se repite al mostrar el formulario y, si vuelve a fallar, lo recoge el límite
  // de error del panel (`app/(panel)/error.tsx`).
  loadSupplierForm().catch(() => undefined);
}

const selectClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto";

const NO_FILTERS: SupplierFilters = { country: "", category: "" };

function matchesFilters(supplier: Supplier, filters: SupplierFilters): boolean {
  return (
    (!filters.country || supplier.country === filters.country) &&
    (!filters.category || supplier.categories.includes(filters.category))
  );
}

export function SupplierDirectory() {
  const [filters, setFilters] = useState<SupplierFilters>(NO_FILTERS);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Cada cambio de filtro pide los datos a la API (GET /suppliers?country=…&category=…), sin recargar la página.
  const list = useApiRequest(
    `${filters.country}|${filters.category}`,
    (signal) => suppliersApi.list(filters, signal),
    (error) => apiErrorMessage(error, "cargar los proveedores")
  );
  const { loading, reload } = list;
  const suppliers = list.data ?? [];
  const activeCount = suppliers.filter((supplier) => supplier.status === "active").length;
  const hasFilters = Boolean(filters.country || filters.category);

  function handleUpdated(updated: Supplier) {
    list.update((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  function handleCreated(created: Supplier) {
    setShowForm(false);
    setNotice(
      `«${created.name}» registrado con el id ${created.id}.` +
        (matchesFilters(created, filters) ? "" : " No aparece en la lista porque no coincide con los filtros aplicados.")
    );
    reload();
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
            : list.error
              ? "Sin datos"
              : `${suppliers.length} ${suppliers.length === 1 ? "proveedor" : "proveedores"} · ${activeCount} activos · ${suppliers.length - activeCount} suspendidos`}
        </p>

        <button
          type="button"
          onClick={() => {
            setNotice(null);
            setShowForm((open) => !open);
          }}
          onPointerEnter={preloadSupplierForm}
          onFocus={preloadSupplierForm}
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
          <Suspense
            fallback={
              <p role="status" className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
                Cargando el formulario…
              </p>
            }
          >
            <DeferredSupplierForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
          </Suspense>
        </div>
      ) : null}

      {list.error && !loading ? (
        <LoadErrorAlert title="No se pudieron cargar los proveedores." message={list.error} onRetry={reload} />
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
