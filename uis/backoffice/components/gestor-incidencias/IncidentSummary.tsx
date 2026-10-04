"use client";

import { useEffect, useState } from "react";
import { ListaBarras } from "@/components/incidencias/ListaBarras";
import { StatCard } from "@/components/StatCard";
import {
  branchLabel,
  INCIDENT_STATUSES,
  incidentCategoryLabel,
  originLabel,
} from "@/lib/data/incidents";
import { entero, porcentaje } from "@/lib/formato";
import { incidentErrorMessage, incidentsApi } from "@/lib/incidents";
import type {
  IncidentBranch,
  IncidentCategory,
  IncidentOrigin,
  IncidentStatus,
  IncidentSummary as IncidentSummaryData,
} from "@/types/incidents";

// En plural: cada tarjeta cuenta incidencias en ese estado.
const STATUS_CARD_LABELS: Record<IncidentStatus, string> = {
  open: "Abiertas",
  in_progress: "En curso",
  resolved: "Resueltas",
  discarded: "Descartadas",
};

interface SummaryResult {
  /** Petición (versión + reintento) a la que corresponde el resultado: si no coincide con la actual, está cargando. */
  key: string;
  summary: IncidentSummaryData | null;
  error: string | null;
}

interface IncidentSummaryProps {
  /** Cambia cuando el listado modifica datos (p. ej. un cambio de estado): el resumen se vuelve a pedir. */
  version: number;
}

/**
 * Totales de `GET /api/incidents/summary`. Tiene su propia petición y sus propios estados de carga y error: si
 * falla, el resto de la página (el listado) sigue funcionando.
 */
export function IncidentSummary({ version }: IncidentSummaryProps) {
  const [retryToken, setRetryToken] = useState(0);
  const [result, setResult] = useState<SummaryResult | null>(null);

  const requestKey = `${version}|${retryToken}`;
  const loading = result?.key !== requestKey;
  // Mientras se actualiza se mantienen los últimos totales, atenuados, en lugar de vaciar el panel.
  const summary = result?.summary ?? null;
  const error = !loading ? (result?.error ?? null) : null;

  useEffect(() => {
    const controller = new AbortController();
    incidentsApi
      .summary(controller.signal)
      .then((data) => setResult({ key: requestKey, summary: data, error: null }))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ key: requestKey, summary: null, error: incidentErrorMessage(reason, "cargar el resumen") });
      });
    return () => controller.abort();
  }, [requestKey]);

  if (error) {
    return (
      <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        <p className="font-bold">No se pudo cargar el resumen.</p>
        <p className="mt-1">{error} El listado sigue disponible.</p>
        <button
          type="button"
          onClick={() => setRetryToken((token) => token + 1)}
          className="mt-3 min-h-11 rounded-full border border-red-300 bg-white px-5 text-sm font-bold text-red-800 transition hover:bg-red-100"
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (!summary) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="rounded-2xl border border-slate-200 bg-white p-5 text-sm font-semibold text-slate-600 shadow-sm"
      >
        Cargando resumen…
      </p>
    );
  }

  const { total } = summary;
  return (
    <div className={`space-y-5 ${loading ? "opacity-60" : ""}`} aria-busy={loading} data-summary-total={total}>
      <p role="status" className="sr-only">
        {loading ? "Actualizando resumen…" : `Resumen actualizado: ${total} incidencias.`}
      </p>

      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Incidencias" value={entero(total)} detail="Total registradas" />
        {INCIDENT_STATUSES.map((status) => (
          <StatCard
            key={status.value}
            label={STATUS_CARD_LABELS[status.value]}
            value={entero(summary.by_status[status.value])}
            detail={porcentaje(summary.by_status[status.value], total)}
          />
        ))}
      </dl>

      {total === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
          Todavía no hay incidencias: los totales por categoría, origen y sede aparecerán al registrar la primera.
        </p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <ListaBarras
            titulo="Por categoría"
            datos={summary.by_category}
            total={total}
            etiqueta={(value) => incidentCategoryLabel(value as IncidentCategory)}
          />
          <div className="space-y-5">
            <ListaBarras
              titulo="Por sede"
              datos={summary.by_branch}
              total={total}
              etiqueta={(value) => branchLabel(value as IncidentBranch)}
            />
            <ListaBarras
              titulo="Por origen"
              datos={summary.by_origin}
              total={total}
              etiqueta={(value) => originLabel(value as IncidentOrigin)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
