export type AreaId =
  | "warehouse"
  | "last-mile"
  | "reverse-logistics"
  | "customer-experience"
  | "commercial"
  | "technology"
  | "executive";

/** Área de negocio de TrackFlow tal y como la describe CONTEXT.es.md. */
export interface BusinessArea {
  id: AreaId;
  name: string;
  /** Responsable. `null` si el CONTEXT no lo identifica (ver memory-bank/projectbrief.md para el caso del CEO). */
  owner: string | null;
  role: string;
  team: string;
  /** Situación actual resumida (problema que resuelve TrackFlow Tech en esa área). */
  situation: string;
}

/**
 * `identified`: necesidad recogida en el CONTEXT, sin implementar.
 * `foundation`: existe ya una base técnica en el repo (hitos anteriores), pero la iniciativa no está completa.
 */
export type InitiativeStatus = "identified" | "foundation";

/** Iniciativa de TrackFlow Tech = una de las necesidades (“Qué necesitan”) de cada área en CONTEXT.es.md. */
export interface Initiative {
  id: string;
  areaId: AreaId;
  title: string;
  detail: string;
  status: InitiativeStatus;
  /** Solo si `status === "foundation"`: qué existe ya y dónde. */
  foundation?: string;
  optional?: boolean;
}

export type MilestoneStatus = "delivered" | "in-progress";

/** Hito del proyecto transversal (fuente: docs/hitos.md y README raíz). */
export interface Milestone {
  number: number;
  name: string;
  status: MilestoneStatus;
  summary: string;
  paths: readonly string[];
  demoUrl?: string;
}

/** Dato de partida documentado en el CONTEXT (no es una métrica en vivo). */
export interface BaselineFact {
  label: string;
  value: string;
  detail: string;
}
