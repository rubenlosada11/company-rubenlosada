import { Badge } from "@/components/Badge";
import {
  branchLabel,
  INCIDENT_TRANSITIONS,
  incidentCategoryLabel,
  incidentStatusLabel,
  originLabel,
  TRANSITION_ACTIONS,
} from "@/lib/data/incidents";
import { formatIncidentDate } from "@/lib/incidents";
import type { Incident, IncidentTargetStatus } from "@/types/incidents";

const STATUS_TONES = { open: "amber", in_progress: "blue", resolved: "emerald", discarded: "neutral" } as const;

const buttonBase =
  "inline-flex min-h-10 items-center justify-center rounded-full px-4 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-60";
const BUTTON_TONES: Record<IncidentTargetStatus, string> = {
  in_progress: "bg-blue-700 text-white hover:bg-blue-800",
  resolved: "bg-emerald-700 text-white hover:bg-emerald-800",
  discarded: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
};

interface IncidentRowProps {
  incident: Incident;
  /** Hay un cambio de estado de esta incidencia esperando la respuesta de la API. */
  saving: boolean;
  error?: string;
  onChangeStatus: (incident: Incident, status: IncidentTargetStatus) => void;
}

export function IncidentRow({ incident, saving, error, onChangeStatus }: IncidentRowProps) {
  const transitions = INCIDENT_TRANSITIONS[incident.status];

  return (
    <tr data-incident-id={incident.id} data-status={incident.status} className="align-top" aria-busy={saving}>
      <td className="px-4 py-4">
        <p className="font-semibold text-slate-900">{incident.title}</p>
        {incident.description !== incident.title ? (
          <p className="mt-1 line-clamp-2 max-w-md text-sm text-slate-600">{incident.description}</p>
        ) : null}
        <p className="mt-1 text-xs text-slate-500">
          N.º {incident.id} · <time dateTime={incident.created_at}>{formatIncidentDate(incident.created_at)}</time>
        </p>
      </td>

      <td className="px-4 py-4">
        <Badge tone="blue">{incidentCategoryLabel(incident.category)}</Badge>
      </td>

      <td className="px-4 py-4 text-sm text-slate-700">
        <p className="font-semibold whitespace-nowrap">{branchLabel(incident.branch)}</p>
        <p className="text-xs text-slate-500">Origen: {originLabel(incident.origin)}</p>
      </td>

      <td className="px-4 py-4">
        <div className="flex flex-col items-start gap-2">
          <Badge tone={STATUS_TONES[incident.status]}>{incidentStatusLabel(incident.status)}</Badge>
          {saving ? <p className="text-xs font-semibold text-slate-500">Guardando…</p> : null}
          {error ? (
            <p role="alert" className="max-w-60 text-xs font-semibold text-red-700">
              {error}
            </p>
          ) : null}
        </div>
      </td>

      <td className="px-4 py-4">
        {transitions.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {transitions.map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => onChangeStatus(incident, status)}
                disabled={saving}
                aria-label={`${TRANSITION_ACTIONS[status]} la incidencia n.º ${incident.id}`}
                className={`${buttonBase} ${BUTTON_TONES[status]}`}
              >
                {TRANSITION_ACTIONS[status]}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500">Estado final</p>
        )}
      </td>
    </tr>
  );
}
