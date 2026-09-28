/**
 * Cliente HTTP mínimo para la API de TrackFlow (`services/api`). Patrón de `uis/talent-pipeline-tracker/lib/http.ts`.
 *
 * `NEXT_PUBLIC_API_BASE_URL` se incrusta al compilar. Si falta, las peticiones fallan con un mensaje claro en la
 * interfaz (no se lanza al importar, para no romper `next build` en entornos sin la variable).
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "");

/** Clave de `fieldErrors` para los errores que no son de un campo concreto (p. ej. moneda y país incoherentes). */
export const FORM_ERROR = "_form";

export class ApiError extends Error {
  status: number;
  /** Errores de validación de FastAPI (422) por campo: `{ rate_per_shipment: "Input should be greater than 0" }`. */
  fieldErrors: Record<string, string>;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

interface FastApiValidationItem {
  loc?: unknown[];
  msg?: unknown;
}

/** Convierte la respuesta de error de FastAPI en un mensaje legible y errores por campo. */
async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return new ApiError(res.statusText || `Error ${res.status}`, res.status);
  }

  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;

  // 404 y similares: { detail: "Proveedor 99 no encontrado" }
  if (typeof detail === "string") return new ApiError(detail, res.status);

  // 422: { detail: [{ loc: ["body", "rate_per_shipment"], msg: "Input should be greater than 0" }, ...] }
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    const messages: string[] = [];
    for (const item of detail as FastApiValidationItem[]) {
      const msg = String(item?.msg ?? "Valor no válido").replace(/^Value error, /, "");
      const path = (item?.loc ?? []).filter((part) => !["body", "query", "path"].includes(String(part)));
      const field = typeof path[0] === "string" ? path[0] : FORM_ERROR;
      fieldErrors[field] ??= msg;
      messages.push(field === FORM_ERROR ? msg : `${field}: ${msg}`);
    }
    return new ApiError(messages.join(" · "), res.status, fieldErrors);
  }

  return new ApiError(res.statusText || `Error ${res.status}`, res.status);
}

/**
 * Petición a la API sin tocar cabeceras ni cuerpo: URL base, error de conexión y respuestas de error como `ApiError`.
 * Devuelve la respuesta sin leer, para cuerpos que no son JSON (subida con `FormData`, descarga de un CSV).
 */
export async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  if (!API_BASE_URL) {
    throw new ApiError(
      "Falta la variable NEXT_PUBLIC_API_BASE_URL. Crea uis/backoffice/.env.local a partir de .env.example y reinicia el backoffice.",
      0
    );
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      `No se pudo conectar con la API de TrackFlow (${API_BASE_URL}). Comprueba que está arrancada.`,
      0
    );
  }

  if (!res.ok) throw await toApiError(res);
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetchApi(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const http = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};
