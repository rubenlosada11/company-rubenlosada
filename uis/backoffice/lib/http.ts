/**
 * Cliente HTTP mínimo para la API de TrackFlow (`services/api`). Patrón de `uis/talent-pipeline-tracker/lib/http.ts`.
 *
 * `NEXT_PUBLIC_API_BASE_URL` se incrusta al compilar. Si falta, las peticiones fallan con un mensaje claro en la
 * interfaz (no se lanza al importar, para no romper `next build` en entornos sin la variable).
 */
import { clearToken, readToken, UNAUTHORIZED_EVENT } from "@/lib/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "");

/** Los detalles de configuración (variable de entorno, URL de la API) solo se muestran en desarrollo. */
const IS_DEVELOPMENT = process.env.NODE_ENV !== "production";

/** Espera máxima de una respuesta: pasado este tiempo la petición se cancela y la interfaz deja de «cargar». */
const REQUEST_TIMEOUT_MS = 20_000;

/** Clave de `fieldErrors` para los errores que no son de un campo concreto (p. ej. moneda y país incoherentes). */
export const FORM_ERROR = "_form";

export const SESSION_EXPIRED_MESSAGE = "Tu sesión ha caducado. Vuelve a iniciar sesión.";
export const SERVER_ERROR_MESSAGE = "El servidor ha tenido un problema. Inténtalo de nuevo en unos minutos.";
const NOT_CONFIGURED_MESSAGE = "El servicio no está disponible en este momento. Inténtalo de nuevo más tarde.";
const CONNECTION_MESSAGE = "No se pudo conectar con la API de TrackFlow. Comprueba tu conexión e inténtalo de nuevo.";
const TIMEOUT_MESSAGE = "La API de TrackFlow tarda demasiado en responder. Inténtalo de nuevo en unos minutos.";
const UNREADABLE_RESPONSE_MESSAGE = "No se pudo leer la respuesta del servidor. Inténtalo de nuevo.";

export class ApiError extends Error {
  /** Código HTTP de la respuesta; 0 si no hubo respuesta (sin conexión, tiempo agotado o API sin configurar). */
  status: number;
  /** Errores de validación de la API (400/422) por campo, ya en español: `{ rate_per_shipment: "Debe ser mayor que 0." }`. */
  fieldErrors: Record<string, string>;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

interface FastApiValidationItem {
  /** Solo en los errores del gestor de incidencias, que la API ya redacta en español. */
  field?: unknown;
  loc?: unknown[];
  msg?: unknown;
}

const INVALID_VALUE = "Valor no válido.";
const OWN_MESSAGE_PREFIX = "Value error, ";

/** Mensajes de validación de Pydantic (en inglés) que puede devolver `services/api`, en español. */
const VALIDATION_MESSAGES: Record<string, string> = {
  "Field required": "Este campo es obligatorio.",
  "Input should be a valid string": "Debe ser un texto.",
  "Input should be a valid number": "Debe ser un número.",
  "Input should be a valid integer": "Debe ser un número entero.",
  "Input should be a finite number": "Debe ser un número.",
  "Extra inputs are not permitted": "La API no admite este campo.",
};

const VALIDATION_PATTERNS: [RegExp, (match: RegExpMatchArray) => string][] = [
  [/^String should have at most (\d+) characters?$/, (m) => `Máximo ${m[1]} caracteres.`],
  [/^String should have at least (\d+) characters?$/, (m) => `Mínimo ${m[1]} caracteres.`],
  [/^List should have at least (\d+) items? after validation/, (m) => `Elige al menos ${m[1]}.`],
  [/^Input should be greater than (-?[\d.]+)$/, (m) => `Debe ser mayor que ${m[1]}.`],
];

/**
 * Mensaje de un error de validación para el usuario. Los que redacta la propia API (`Value error, …` y los del gestor
 * de incidencias) ya están en español y se respetan; los de Pydantic se traducen y, si no se conocen, se sustituyen por
 * un texto fijo: nunca se muestra un mensaje técnico en inglés.
 */
function validationMessage(item: FastApiValidationItem): string {
  const raw = typeof item?.msg === "string" ? item.msg.trim() : "";
  if (!raw) return INVALID_VALUE;
  if (raw.startsWith(OWN_MESSAGE_PREFIX)) return raw.slice(OWN_MESSAGE_PREFIX.length);
  if (item.field !== undefined) return raw;
  if (VALIDATION_MESSAGES[raw]) return VALIDATION_MESSAGES[raw];
  for (const [pattern, build] of VALIDATION_PATTERNS) {
    const match = raw.match(pattern);
    if (match) return build(match);
  }
  return INVALID_VALUE;
}

/** Mensaje para una respuesta de error sin un `detail` que se pueda mostrar. */
function defaultMessage(status: number): string {
  if (status === 401) return SESSION_EXPIRED_MESSAGE;
  if (status === 403) return "No tienes permiso para hacer esta operación.";
  if (status === 404) return "No se ha encontrado lo que buscabas.";
  if (status >= 500) return SERVER_ERROR_MESSAGE;
  return "No se ha podido completar la operación. Inténtalo de nuevo.";
}

/** Convierte la respuesta de error de FastAPI en un mensaje legible y errores por campo. */
async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    // Cuerpo vacío o que no es JSON (p. ej. la página de error de un proxy): no hay nada que mostrar de él.
    return new ApiError(defaultMessage(res.status), res.status);
  }

  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;

  // 404 y similares: { detail: "Proveedor 99 no encontrado" }
  if (typeof detail === "string" && detail.trim()) return new ApiError(detail, res.status);

  // 422: { detail: [{ loc: ["body", "rate_per_shipment"], msg: "Input should be greater than 0" }, ...] }
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const item of detail as FastApiValidationItem[]) {
      const path = (item?.loc ?? []).filter((part) => !["body", "query", "path"].includes(String(part)));
      const field = typeof path[0] === "string" ? path[0] : FORM_ERROR;
      fieldErrors[field] ??= validationMessage(item);
    }
    const message = fieldErrors[FORM_ERROR] ?? "Revisa los datos y vuelve a intentarlo.";
    return new ApiError(message, res.status, fieldErrors);
  }

  return new ApiError(defaultMessage(res.status), res.status);
}

/**
 * Mensaje para el usuario a partir de cualquier error de una llamada a la API. `action` completa la frase
 * («No se ha podido cargar los proveedores…»). Nunca devuelve trazas, JSON, códigos HTTP ni mensajes internos: los
 * errores del servidor (5xx) y los desconocidos se sustituyen por un texto fijo.
 */
export function apiErrorMessage(error: unknown, action: string): string {
  if (!(error instanceof ApiError)) return `No se ha podido ${action}. Inténtalo de nuevo.`;
  // Sin conexión, tiempo agotado o API sin configurar: este módulo ya da un mensaje pensado para la interfaz.
  if (error.status === 0) return error.message;
  if (error.status === 401) return SESSION_EXPIRED_MESSAGE;
  if (error.status >= 500) {
    return `No se ha podido ${action} por un problema del servidor. Inténtalo de nuevo en unos minutos.`;
  }
  // 4xx: el `detail` que redacta la API en español o, si no lo había, el texto por defecto de su código.
  return error.message;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export interface ApiOptions {
  /**
   * `true` (por defecto): petición protegida; envía el Bearer token y un 401 cierra la sesión.
   * `false`: endpoint público (login, registro); sin token, y su 401/403 es un error normal del formulario.
   */
  auth?: boolean;
}

/**
 * Petición a la API sin tocar el cuerpo: URL base, token Bearer, error de conexión y respuestas de error como
 * `ApiError`. Devuelve la respuesta sin leer, para cuerpos que no son JSON (subida con `FormData`, descarga de un CSV).
 *
 * Si la API responde 401 a una petición protegida (token caducado, revocado o ausente), se borra el token y se avisa
 * con `UNAUTHORIZED_EVENT` para volver al login. También sin token: así no queda un estado «autenticado» falso si el
 * token desaparece con la aplicación abierta.
 */
export async function fetchApi(path: string, init?: RequestInit, { auth = true }: ApiOptions = {}): Promise<Response> {
  if (!API_BASE_URL) {
    throw new ApiError(
      IS_DEVELOPMENT
        ? "Falta la variable NEXT_PUBLIC_API_BASE_URL. Crea uis/backoffice/.env.local a partir de .env.example y reinicia el backoffice."
        : NOT_CONFIGURED_MESSAGE,
      0
    );
  }

  const token = auth ? readToken() : null;
  const headers = new Headers(init?.headers);
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);

  // La petición se cancela si quien llama la aborta (cambio de filtros, desmontaje) o si se agota el tiempo de espera.
  const caller = init?.signal;
  const controller = new AbortController();
  let timedOut = false;
  if (caller?.aborted) controller.abort();
  // El aviso de quien llama sigue activo tras recibir las cabeceras: también cancela la lectura del cuerpo.
  caller?.addEventListener("abort", () => controller.abort(), { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new ApiError(TIMEOUT_MESSAGE, 0);
    if (isAbortError(error)) throw error;
    throw new ApiError(
      IS_DEVELOPMENT
        ? `No se pudo conectar con la API de TrackFlow (${API_BASE_URL}). Comprueba que está arrancada.`
        : CONNECTION_MESSAGE,
      0
    );
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401 && auth) {
    clearToken();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) throw await toApiError(res);
  return res;
}

/**
 * Lee el cuerpo JSON de una respuesta correcta. Si no es JSON (p. ej. un proxy devuelve HTML con un 200), lanza un
 * `ApiError` legible en lugar del `SyntaxError` del navegador («Unexpected token…»).
 */
export async function readJson<T>(res: Response): Promise<T> {
  try {
    return (await res.json()) as T;
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(UNREADABLE_RESPONSE_MESSAGE, res.status);
  }
}

async function request<T>(path: string, init?: RequestInit, options?: ApiOptions): Promise<T> {
  const res = await fetchApi(
    path,
    {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    },
    options
  );
  if (res.status === 204) return undefined as T;
  return readJson<T>(res);
}

export const http = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body: unknown, options?: ApiOptions) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }, options),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};
