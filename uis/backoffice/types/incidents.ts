// Gestor de incidencias (`/api/incidents` en services/api). Valores de CONTEXT-gestor-incidencias.es.md.
// No confundir con `types/incidencias.ts`, que es la respuesta del analizador de CSV.

export type IncidentCategory =
  | "lost_parcel"
  | "delivery_failure"
  | "inventory_discrepancy"
  | "carrier_issue"
  | "returns_issue"
  | "warehouse_incident"
  | "system_failure"
  | "client_complaint"
  | "other";

export type IncidentStatus = "open" | "in_progress" | "resolved" | "discarded";

/** Estados a los que puede pasar una incidencia: ninguna transición vuelve a `open`. */
export type IncidentTargetStatus = Exclude<IncidentStatus, "open">;

export type IncidentOrigin = "customer" | "branch" | "internal";

export type IncidentBranch = "central" | "la_warehouse" | "la_office" | "zaragoza_warehouse" | "zaragoza_office";

/** Cuerpo de `POST /api/incidents`. El estado y las fechas los pone la API. */
export interface IncidentCreatePayload {
  title: string;
  description: string;
  category: IncidentCategory;
  origin: IncidentOrigin;
  branch: IncidentBranch;
}

/** Filtros de `GET /api/incidents`; cadena vacía = sin filtrar por ese campo. */
export interface IncidentFilters {
  status: IncidentStatus | "";
  origin: IncidentOrigin | "";
  branch: IncidentBranch | "";
  category: IncidentCategory | "";
}

/** Respuesta de `GET /api/incidents/summary`: cada bloque trae todos los valores posibles, a 0 si no hay datos. */
export interface IncidentSummary {
  total: number;
  by_status: Record<IncidentStatus, number>;
  by_category: Record<IncidentCategory, number>;
  by_origin: Record<IncidentOrigin, number>;
  by_branch: Record<IncidentBranch, number>;
}

export interface Incident extends IncidentCreatePayload {
  id: number;
  status: IncidentStatus;
  created_at: string;
  updated_at: string;
}
