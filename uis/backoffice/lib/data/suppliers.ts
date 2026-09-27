import type { SupplierCategory, SupplierCountry, SupplierCurrency, SupplierStatus } from "@/types";

/**
 * Valores válidos del directorio de proveedores, copiados de CONTEXT-directorio.md (los mismos enums que valida la
 * API). Las etiquetas son solo la traducción al español de cada código para la interfaz.
 */

export const SUPPLIER_COUNTRIES: readonly { value: SupplierCountry; label: string }[] = [
  { value: "USA", label: "EE. UU." },
  { value: "Spain", label: "España" },
];

/** Restricción de negocio del CONTEXT: la moneda del contrato la fija el país. */
export const CURRENCY_BY_COUNTRY: Record<SupplierCountry, SupplierCurrency> = {
  USA: "USD",
  Spain: "EUR",
};

export const SUPPLIER_CATEGORIES: readonly { value: SupplierCategory; label: string }[] = [
  { value: "carrier_last_mile", label: "Carrier de última milla" },
  { value: "carrier_international", label: "Carrier internacional" },
  { value: "warehouse_supplies", label: "Suministros de almacén" },
  { value: "packaging_materials", label: "Material de embalaje" },
  { value: "reverse_logistics", label: "Logística inversa" },
  { value: "fleet_maintenance", label: "Mantenimiento de flota" },
  { value: "it_and_wms_software", label: "Software IT y SGA" },
  { value: "cleaning_and_facilities", label: "Limpieza e instalaciones" },
];

export const SUPPLIER_STATUSES: readonly { value: SupplierStatus; label: string }[] = [
  { value: "active", label: "Activo" },
  { value: "suspended", label: "Suspendido" },
];

const labelOf = <T extends string>(list: readonly { value: T; label: string }[], value: T) =>
  list.find((item) => item.value === value)?.label ?? value;

export const countryLabel = (value: SupplierCountry) => labelOf(SUPPLIER_COUNTRIES, value);
export const categoryLabel = (value: SupplierCategory) => labelOf(SUPPLIER_CATEGORIES, value);
export const statusLabel = (value: SupplierStatus) => labelOf(SUPPLIER_STATUSES, value);
