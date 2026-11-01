import type { Category, ExitType, Warehouse } from "@/types/inventory";

/**
 * Valores válidos del inventario, de CONTEXT-gestor-inventario.es.md (los mismos que valida la API). Los almacenes son
 * los del CONTEXT («Los Ángeles», «Zaragoza»); las categorías siguen su descripción del negocio («moda, electrónica y
 * cosmética»); los tipos de salida, sus definiciones («despacho», «pérdida»).
 */

export const WAREHOUSES: readonly { value: Warehouse; label: string }[] = [
  { value: "LA", label: "Los Ángeles" },
  { value: "ZGZ", label: "Zaragoza" },
];

export const CATEGORIES: readonly { value: Category; label: string }[] = [
  { value: "fashion", label: "Moda" },
  { value: "electronics", label: "Electrónica" },
  { value: "cosmetics", label: "Cosmética" },
];

export const EXIT_TYPES: readonly { value: ExitType; label: string; hint: string }[] = [
  { value: "dispatch", label: "Despacho", hint: "Envío a cliente. Requiere el número de seguimiento del transportista." },
  { value: "loss", label: "Pérdida", hint: "Discrepancia o daño confirmado. Sin número de seguimiento." },
];

function labelOf<T extends string>(options: readonly { value: T; label: string }[], value: T): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

/** «Los Ángeles (LA)». Si la API devolviera un valor desconocido, se muestra tal cual. */
export const warehouseLabel = (value: Warehouse) => `${labelOf(WAREHOUSES, value)} (${value})`;
export const categoryLabel = (value: Category) => labelOf(CATEGORIES, value);
export const exitTypeLabel = (value: ExitType) => labelOf(EXIT_TYPES, value);
