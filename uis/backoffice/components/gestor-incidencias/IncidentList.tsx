"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { INCIDENT_BRANCHES, INCIDENT_CATEGORIES, INCIDENT_ORIGINS, INCIDENT_STATUSES } from "@/lib/data/incidents";
import { ApiError } from "@/lib/http";
import { incidentErrorMessage, incidentsApi, NO_INCIDENT_FILTERS } from "@/lib/incidents";
import type { Incident, IncidentFilters, IncidentTargetStatus } from "@/types/incidents";
import { IncidentRow } from "./IncidentRow";

const selectClasses =
  "min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto";
const filterLabelClasses = "text-xs font-bold tracking-wide text-slate-500 uppercase";

const FILTERS = [
  { field: "status", label: "Estado", all: "Todos los estados", options: INCIDENT_STATUSES },
  { field: "origin", label: "Origen", all: "Todos los orígenes", options: INCIDENT_ORIGINS },
  { field: "branch", label: "Sede", all: "Todas las sedes", options: INCIDENT_BRANCHES },
  { field: "category", label: "Categoría", all: "Todas las categorías", options: INCIDENT_CATEGORIES },
] as const;

interface ListResult {
  /** Petición (filtros + recarga) a la que corresponde el resultado: si no coincide con la actual, está cargando. */
  key: string;
  incidents: Incident[];
  error: string | null;
}

interface IncidentListProps {
  /** Los datos han cambiado en la API (cambio de estado) o se ha pedido actualizar: quien dependa de ellos se refresca. */
  onChanged?: () => void;
}

export function IncidentList({ onChanged }: IncidentListProps) {
  const [filters, setFilters] = useState<IncidentFilters>(NO_INCIDENT_FILTERS);
  const [reloadToken, setReloadToken] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  // El estado tarda un render en deshabilitar los botones: la referencia evita dos cambios seguidos de una fila.
  const savingRef = useRef(new Set<number>());

  const requestKey = `${Object.values(filters).join("|")}|${reloadToken}`;
  const loading = result?.key !== requestKey;
  const incidents = result?.incidents ?? [];
  const hasFilters = Object.values(filters).some(Boolean);

  // Cada cambio de filtro pide los datos a la API (GET /api/incidents?status=…), sin recargar la página.
  useEffect(() => {
    const controller = new AbortController();
    incidentsApi
      .list(filters, controller.signal)
      .then((list) => {
        setRowErrors({});
        setResult({ key: requestKey, incidents: list, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ key: requestKey, incidents: [], error: incidentErrorMessage(error, "cargar el listado") });
      });
    return () => controller.abort();
  }, [filters, requestKey]);

  function replaceIncident(incident: Incident) {
    setResult((current) =>
      current
        ? { ...current, incidents: current.incidents.map((item) => (item.id === incident.id ? incident : item)) }
        : current
    );
  }

  function setRowError(id: number, message: string | null) {
    setRowErrors((current) => {
      const rest = { ...current };
      delete rest[id];
      return message ? { ...rest, [id]: message } : rest;
    });
  }

  /** Cambio optimista: la fila muestra el estado nuevo al momento y vuelve al anterior si la API lo rechaza. */
  async function changeStatus(incident: Incident, status: IncidentTargetStatus) {
    if (savingRef.current.has(incident.id)) return;
    savingRef.current.add(incident.id);
    setSaving((current) => ({ ...current, [incident.id]: true }));
    setRowError(incident.id, null);
    replaceIncident({ ...incident, status });

    try {
      replaceIncident(await incidentsApi.updateStatus(incident.id, status));
      onChanged?.();
    } catch (error) {
      replaceIncident(incident);
      // Transición rechazada (400): la API explica el motivo en español en el campo `status`.
      const reason = error instanceof ApiError && error.status === 400 ? error.fieldErrors.status : undefined;
      setRowError(
        incident.id,
        reason
          ? `${reason} Actualiza el listado para ver su estado actual.`
          : incidentErrorMessage(error, "cambiar el estado")
      );
    } finally {
      savingRef.current.delete(incident.id);
      setSaving((current) => {
        const rest = { ...current };
        delete rest[incident.id];
        return rest;
      });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
        {FILTERS.map((filter) => (
          <div key={filter.field} className="flex flex-col gap-1.5">
            <label htmlFor={`incident-filter-${filter.field}`} className={filterLabelClasses}>
              {filter.label}
            </label>
            <select
              id={`incident-filter-${filter.field}`}
              value={filters[filter.field]}
              onChange={(event) => setFilters((current) => ({ ...current, [filter.field]: event.target.value }))}
              className={selectClasses}
            >
              <option value="">{filter.all}</option>
              {filter.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ))}

        {hasFilters ? (
          <button
            type="button"
            onClick={() => setFilters(NO_INCIDENT_FILTERS)}
            className="min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
          >
            Quitar filtros
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => {
            setReloadToken((token) => token + 1);
            onChanged?.();
          }}
          disabled={loading}
          className="min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
        >
          Actualizar
        </button>

        <Link
          href="/gestor-incidencias/nueva"
          className="inline-flex min-h-11 items-center justify-center rounded-full bg-blue-700 px-5 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:ml-auto"
        >
          Registrar incidencia
        </Link>
      </div>

      <p role="status" className="text-sm font-semibold text-slate-600">
        {loading
          ? "Cargando incidencias…"
          : result?.error
            ? "Sin datos"
            : `${incidents.length} ${incidents.length === 1 ? "incidencia" : "incidencias"}${hasFilters ? " con los filtros aplicados" : ""}`}
      </p>

      {result?.error && !loading ? (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p className="font-bold">No se pudieron cargar las incidencias.</p>
          <p className="mt-1">{result.error}</p>
          <button
            type="button"
            onClick={() => setReloadToken((token) => token + 1)}
            className="mt-3 min-h-11 rounded-full border border-red-300 bg-white px-5 text-sm font-bold text-red-800 transition hover:bg-red-100"
          >
            Reintentar
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className={`w-full min-w-[920px] text-left ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <caption className="sr-only">Incidencias registradas en TrackFlow</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold tracking-wide text-slate-500 uppercase">
              <tr>
                <th scope="col" className="px-4 py-3">Incidencia</th>
                <th scope="col" className="px-4 py-3">Categoría</th>
                <th scope="col" className="px-4 py-3">Sede</th>
                <th scope="col" className="px-4 py-3">Estado</th>
                <th scope="col" className="px-4 py-3">Cambiar estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {incidents.map((incident) => (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  saving={Boolean(saving[incident.id])}
                  error={rowErrors[incident.id]}
                  onChangeStatus={changeStatus}
                />
              ))}
              {loading && incidents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-600">
                    Cargando incidencias…
                  </td>
                </tr>
              ) : null}
              {!loading && incidents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-600">
                    {hasFilters
                      ? "Ninguna incidencia coincide con los filtros seleccionados."
                      : "Todavía no hay incidencias registradas. Registra la primera con el botón «Registrar incidencia»."}
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
