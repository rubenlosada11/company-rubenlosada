import { ApiError, http } from "@/lib/http";
import type {
  Incident,
  IncidentBranch,
  IncidentCategory,
  IncidentCreatePayload,
  IncidentFilters,
  IncidentOrigin,
  IncidentSummary,
  IncidentTargetStatus,
} from "@/types/incidents";

/** Llamadas al gestor de incidencias de `services/api`. */
export const incidentsApi = {
  create(payload: IncidentCreatePayload): Promise<Incident> {
    return http.post<Incident>("/api/incidents", payload);
  },

  list(filters: IncidentFilters, signal?: AbortSignal): Promise<Incident[]> {
    const params = new URLSearchParams();
    for (const [field, value] of Object.entries(filters)) {
      if (value) params.set(field, value);
    }
    const query = params.toString();
    return http.get<Incident[]>(`/api/incidents${query ? `?${query}` : ""}`, signal);
  },

  updateStatus(id: number, status: IncidentTargetStatus): Promise<Incident> {
    return http.patch<Incident>(`/api/incidents/${id}/status`, { status });
  },

  summary(signal?: AbortSignal): Promise<IncidentSummary> {
    return http.get<IncidentSummary>("/api/incidents/summary", signal);
  },
};

export const NO_INCIDENT_FILTERS: IncidentFilters = { status: "", origin: "", branch: "", category: "" };

export function formatIncidentDate(iso: string): string {
  const date = new Date(iso);
  // `format` lanza `RangeError` con una fecha no válida, y eso rompería el render de todo el listado.
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

/** Mismos límites que la API (`gestor.py` del paquete compartido). */
export const TITLE_MAX_LENGTH = 120;
export const DESCRIPTION_MAX_LENGTH = 2000;

export interface IncidentDraft {
  title: string;
  description: string;
  category: IncidentCategory | "";
  origin: IncidentOrigin | "";
  branch: IncidentBranch | "";
}

export const EMPTY_INCIDENT_DRAFT: IncidentDraft = {
  title: "",
  description: "",
  category: "",
  origin: "",
  branch: "",
};

/** Campos del formulario, en el orden en que aparecen (para llevar el foco al primero con error). */
export const INCIDENT_FIELDS = ["title", "description", "category", "origin", "branch"] as const;
export type IncidentField = (typeof INCIDENT_FIELDS)[number];

/**
 * Validación en cliente con los mismos mensajes que la API, que vuelve a validarlo todo (400). Las claves de `errors`
 * coinciden con los campos de la API para mostrar en el mismo sitio los errores que devuelva.
 */
export function validateIncidentDraft(draft: IncidentDraft): {
  payload: IncidentCreatePayload | null;
  errors: Record<string, string>;
} {
  const errors: Record<string, string> = {};
  const title = draft.title.trim();
  const description = draft.description.trim();

  if (!title) errors.title = "El título es obligatorio.";
  else if (title.length > TITLE_MAX_LENGTH)
    errors.title = `El título no puede superar los ${TITLE_MAX_LENGTH} caracteres.`;

  if (!description) errors.description = "La descripción es obligatoria.";
  else if (description.length > DESCRIPTION_MAX_LENGTH)
    errors.description = `La descripción no puede superar los ${DESCRIPTION_MAX_LENGTH} caracteres.`;

  if (!draft.category) errors.category = "La categoría es obligatoria.";
  if (!draft.origin) errors.origin = "El origen es obligatorio.";
  if (!draft.branch) errors.branch = "La sede es obligatoria.";

  if (Object.keys(errors).length > 0 || !draft.category || !draft.origin || !draft.branch) {
    return { payload: null, errors };
  }
  return {
    errors,
    payload: { title, description, category: draft.category, origin: draft.origin, branch: draft.branch },
  };
}

/**
 * Mensaje para el usuario a partir de un error de la API. Nunca muestra trazas, JSON ni mensajes internos: los
 * errores del servidor (5xx) y los desconocidos se sustituyen por un texto fijo.
 */
export function incidentErrorMessage(error: unknown, action: string): string {
  if (!(error instanceof ApiError)) return `No se ha podido ${action}. Inténtalo de nuevo.`;
  // Sin conexión o sin configurar: `lib/http.ts` ya da un mensaje pensado para la interfaz.
  if (error.status === 0) return error.message;
  if (error.status === 401) return "Tu sesión ha caducado. Vuelve a iniciar sesión.";
  if (error.status === 400 || error.status === 422) return "Revisa los campos marcados y vuelve a intentarlo.";
  if (error.status === 404) return "La incidencia ya no existe. Actualiza el listado.";
  return `No se ha podido ${action} por un problema del servidor. Inténtalo de nuevo en unos minutos.`;
}
