import type {
  IncidentBranch,
  IncidentCategory,
  IncidentOrigin,
  IncidentStatus,
  IncidentTargetStatus,
} from "@/types/incidents";

/**
 * Valores válidos del gestor de incidencias, copiados de CONTEXT-gestor-incidencias.es.md (los mismos que valida la
 * API). Las etiquetas de las sedes son literales del CONTEXT; las de categorías, orígenes y estados son la traducción
 * al español de cada código, y las descripciones (`hint`) resumen las del CONTEXT.
 */

export const INCIDENT_BRANCHES: readonly { value: IncidentBranch; label: string }[] = [
  { value: "central", label: "Central" },
  { value: "la_warehouse", label: "Los Ángeles — Almacén" },
  { value: "la_office", label: "Los Ángeles — Oficina" },
  { value: "zaragoza_warehouse", label: "Zaragoza — Almacén" },
  { value: "zaragoza_office", label: "Zaragoza — Oficina" },
];

export const INCIDENT_CATEGORIES: readonly { value: IncidentCategory; label: string }[] = [
  { value: "lost_parcel", label: "Paquete extraviado" },
  { value: "delivery_failure", label: "Fallo de entrega" },
  { value: "inventory_discrepancy", label: "Discrepancia de inventario" },
  { value: "carrier_issue", label: "Problema con el carrier" },
  { value: "returns_issue", label: "Problema en una devolución" },
  { value: "warehouse_incident", label: "Incidente en almacén" },
  { value: "system_failure", label: "Fallo de sistema" },
  { value: "client_complaint", label: "Queja de empresa cliente" },
  { value: "other", label: "Otra" },
];

export const INCIDENT_ORIGINS: readonly { value: IncidentOrigin; label: string; hint: string }[] = [
  { value: "customer", label: "Cliente", hint: "La reporta una empresa cliente o un consumidor final." },
  { value: "branch", label: "Sede", hint: "La detecta personal de un almacén u oficina." },
  { value: "internal", label: "Interno", hint: "La detecta tecnología, dirección u operaciones." },
];

export const INCIDENT_STATUSES: readonly { value: IncidentStatus; label: string }[] = [
  { value: "open", label: "Abierta" },
  { value: "in_progress", label: "En curso" },
  { value: "resolved", label: "Resuelta" },
  { value: "discarded", label: "Descartada" },
];

/** Ciclo de vida del CONTEXT: estado actual → estados a los que puede pasar. `resolved` y `discarded` son finales. */
export const INCIDENT_TRANSITIONS: Record<IncidentStatus, readonly IncidentTargetStatus[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded"],
  resolved: [],
  discarded: [],
};

/** Texto del botón que lleva la incidencia a cada estado. */
export const TRANSITION_ACTIONS: Record<IncidentTargetStatus, string> = {
  in_progress: "Empezar",
  resolved: "Resolver",
  discarded: "Descartar",
};

const labelOf = <T extends string>(list: readonly { value: T; label: string }[], value: T) =>
  list.find((item) => item.value === value)?.label ?? value;

export const branchLabel = (value: IncidentBranch) => labelOf(INCIDENT_BRANCHES, value);
export const incidentCategoryLabel = (value: IncidentCategory) => labelOf(INCIDENT_CATEGORIES, value);
export const originLabel = (value: IncidentOrigin) => labelOf(INCIDENT_ORIGINS, value);
export const incidentStatusLabel = (value: IncidentStatus) => labelOf(INCIDENT_STATUSES, value);
