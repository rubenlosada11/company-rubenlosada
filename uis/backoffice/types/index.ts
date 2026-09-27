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

/** Demo pública en producción de un hito (un hito puede tener varias, p. ej. website y backoffice). */
export interface Demo {
  label: string;
  url: string;
}

/** Hito del proyecto transversal (fuente: docs/hitos.md y README raíz). */
export interface Milestone {
  number: number;
  name: string;
  status: MilestoneStatus;
  summary: string;
  paths: readonly string[];
  demos?: readonly Demo[];
}

/** Dato de partida documentado en el CONTEXT (no es una métrica en vivo). */
export interface BaselineFact {
  label: string;
  value: string;
  detail: string;
}

/* --- Directorio de proveedores (API `services/api`, contrato de CONTEXT-directorio.md) --- */

export type SupplierCountry = "USA" | "Spain";
export type SupplierCurrency = "USD" | "EUR";
export type SupplierStatus = "active" | "suspended";
export type SupplierCategory =
  | "carrier_last_mile"
  | "carrier_international"
  | "warehouse_supplies"
  | "packaging_materials"
  | "reverse_logistics"
  | "fleet_maintenance"
  | "it_and_wms_software"
  | "cleaning_and_facilities";

/** Proveedor tal y como lo devuelve la API. `id` y `updated_at` los genera el servidor. */
export interface Supplier {
  id: number;
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  rate_per_shipment: number;
  currency: SupplierCurrency;
  status: SupplierStatus;
  service_zone: string | null;
  contact_email: string | null;
  notes: string | null;
  /** ISO 8601 (UTC): última actualización de tarifa. */
  updated_at: string;
}

/** Cuerpo de `POST /suppliers`: sin `id` ni `updated_at`. */
export type SupplierCreatePayload = Omit<Supplier, "id" | "updated_at">;

export interface SupplierFilters {
  country: SupplierCountry | "";
  category: SupplierCategory | "";
}
