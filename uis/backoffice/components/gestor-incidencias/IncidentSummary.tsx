"use client";

import { ListaBarras } from "@/components/incidencias/ListaBarras";
import { LoadErrorAlert } from "@/components/LoadErrorAlert";
import { StatCard } from "@/components/StatCard";
import {
  branchLabel,
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  incidentCategoryLabel,
  originLabel,
} from "@/lib/data/incidents";
import { entero, porcentaje } from "@/lib/formato";
import { incidentErrorMessage, incidentsApi } from "@/lib/incidents";
import { useApiRequest } from "@/lib/useApiRequest";
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

interface IncidentSummaryProps {
  /** Cambia cuando el listado modifica datos (p. ej. un cambio de estado): el resumen se vuelve a pedir. */
  version: number;
}

/**
 * Totales de `GET /api/incidents/summary`. Tiene su propia petición y sus propios estados de carga y error: si
 * falla, el resto de la página (el listado) sigue funcionando.
 */
export function IncidentSummary({ version }: IncidentSummaryProps) {
  const request = useApiRequest(String(version), (signal) => incidentsApi.summary(signal), (reason) =>
    incidentErrorMessage(reason, "cargar el resumen")
  );
  const { loading, reload } = request;
  // Mientras se actualiza se mantienen los últimos totales, atenuados, en lugar de vaciar el panel.
  const summary = request.data;
  const error = !loading ? request.error : null;

  if (error) {
    return (
      <LoadErrorAlert
        title="No se pudo cargar el resumen."
        message={`${error} El listado sigue disponible.`}
        onRetry={reload}
      />
    );
  }

  if (!summary) {
    // Primera carga: se reserva el alto exacto del resumen (la misma estructura, invisible) para que el listado de
    // debajo no salte al llegar los datos (CLS). Encima, el aviso de carga.
    return (
      <div className="relative" aria-busy="true">
        <p
          role="status"
          className="absolute inset-x-0 top-0 z-10 rounded-2xl border border-slate-200 bg-white p-5 text-sm font-semibold text-slate-600 shadow-sm"
        >
          Cargando resumen…
        </p>
        <div className="invisible" aria-hidden="true">
          <SummaryContent summary={PLACEHOLDER_SUMMARY} />
        </div>
      </div>
    );
  }

  const { total } = summary;
  return (
    <div className={`space-y-5 ${loading ? "opacity-60" : ""}`} aria-busy={loading} data-summary-total={total}>
      <p role="status" className="sr-only">
        {loading ? "Actualizando resumen…" : `Resumen actualizado: ${total} incidencias.`}
      </p>
      <SummaryContent summary={summary} />
    </div>
  );
}

/** Ceros con todas las claves que devuelve la API: misma estructura (y alto) que el resumen real. */
const zeros = <K extends string>(options: readonly { value: K }[]) =>
  Object.fromEntries(options.map((option) => [option.value, 0])) as Record<K, number>;

const PLACEHOLDER_SUMMARY: IncidentSummaryData = {
  // Con `total` > 0 se pinta la variante con barras, que es la que tendrá la página con incidencias.
  total: 1,
  by_status: zeros(INCIDENT_STATUSES),
  by_category: zeros(INCIDENT_CATEGORIES),
  by_origin: zeros(INCIDENT_ORIGINS),
  by_branch: zeros(INCIDENT_BRANCHES),
};

function SummaryContent({ summary }: { summary: IncidentSummaryData }) {
  const { total } = summary;
  return (
    <div className="space-y-5">
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
