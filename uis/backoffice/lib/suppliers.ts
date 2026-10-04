import { CURRENCY_BY_COUNTRY } from "@/lib/data/suppliers";
import { http } from "@/lib/http";
import type {
  Supplier,
  SupplierCategory,
  SupplierCountry,
  SupplierCreatePayload,
  SupplierFilters,
  SupplierStatus,
} from "@/types";

/** Llamadas a `services/api`. El backoffice no borra proveedores: el flujo de TrackFlow es suspenderlos. */
export const suppliersApi = {
  list(filters: SupplierFilters, signal?: AbortSignal): Promise<Supplier[]> {
    const params = new URLSearchParams();
    if (filters.country) params.set("country", filters.country);
    if (filters.category) params.set("category", filters.category);
    const query = params.toString();
    return http.get<Supplier[]>(`/suppliers${query ? `?${query}` : ""}`, signal);
  },

  create(payload: SupplierCreatePayload): Promise<Supplier> {
    return http.post<Supplier>("/suppliers", payload);
  },

  updateRate(id: number, rate: number): Promise<Supplier> {
    return http.patch<Supplier>(`/suppliers/${id}/rate`, { rate_per_shipment: rate });
  },

  updateStatus(id: number, status: SupplierStatus): Promise<Supplier> {
    return http.patch<Supplier>(`/suppliers/${id}/status`, { status });
  },
};

/** Misma validación básica de email que la API (`app/models.py`). */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Tarifa escrita por el usuario → número > 0, o `null` si no es válida. Acepta coma decimal. */
export function parseRate(value: string): number | null {
  const rate = Number(value.trim().replace(",", "."));
  return value.trim() !== "" && Number.isFinite(rate) && rate > 0 ? rate : null;
}

export interface SupplierDraft {
  name: string;
  country: SupplierCountry | "";
  categories: SupplierCategory[];
  rate: string;
  status: SupplierStatus;
  service_zone: string;
  contact_email: string;
  notes: string;
}

export const EMPTY_DRAFT: SupplierDraft = {
  name: "",
  country: "",
  categories: [],
  rate: "",
  status: "active",
  service_zone: "",
  contact_email: "",
  notes: "",
};

/**
 * Validación en cliente de lo razonablemente comprobable. La API vuelve a validarlo todo (422). Las claves de
 * `errors` coinciden con los campos de la API para mostrar en el mismo sitio los errores de FastAPI.
 */
export function validateDraft(draft: SupplierDraft): {
  payload: SupplierCreatePayload | null;
  errors: Record<string, string>;
} {
  const errors: Record<string, string> = {};
  const rate = parseRate(draft.rate);
  const email = draft.contact_email.trim();

  if (!draft.name.trim()) errors.name = "El nombre es obligatorio.";
  if (!draft.country) errors.country = "Elige el país del contrato.";
  if (draft.categories.length === 0) errors.categories = "Elige al menos una categoría.";
  if (rate === null) errors.rate_per_shipment = "La tarifa debe ser un número mayor que 0.";
  if (email && !EMAIL_PATTERN.test(email)) errors.contact_email = "El email no tiene un formato válido.";

  if (Object.keys(errors).length > 0 || !draft.country || rate === null) return { payload: null, errors };

  return {
    errors,
    payload: {
      name: draft.name.trim(),
      country: draft.country,
      categories: draft.categories,
      rate_per_shipment: rate,
      currency: CURRENCY_BY_COUNTRY[draft.country],
      status: draft.status,
      service_zone: draft.service_zone.trim() || null,
      contact_email: email || null,
      notes: draft.notes.trim() || null,
    },
  };
}

export function formatRate(supplier: Pick<Supplier, "rate_per_shipment" | "currency">): string {
  try {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: supplier.currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(supplier.rate_per_shipment);
  } catch {
    // `Intl` lanza `RangeError` con un código de moneda que no reconoce: se muestra la tarifa sin formato de moneda.
    return `${supplier.rate_per_shipment} ${supplier.currency ?? ""}`.trim();
  }
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  // `format` lanza `RangeError` con una fecha no válida, y eso rompería el render de toda la tabla.
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" }).format(date);
}
