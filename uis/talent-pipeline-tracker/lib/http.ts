const API_URL = process.env.NEXT_PUBLIC_API_URL;

if (!API_URL) {
  throw new Error(
    "Falta la variable de entorno NEXT_PUBLIC_API_URL. Define .env.local a partir de .env.example."
  );
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Extrae un mensaje legible de los distintos formatos de error que devuelve la API. */
async function parseErrorMessage(res: Response): Promise<string> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return res.statusText || `Error ${res.status}`;
  }

  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;

    // Forma FastAPI: { detail: [{ loc, msg, type }, ...] }
    if (Array.isArray(obj.detail)) {
      const messages = obj.detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const loc = Array.isArray((item as { loc?: unknown[] }).loc)
              ? (item as { loc: unknown[] }).loc.filter((part) => part !== "body").join(".")
              : "";
            const msg = String((item as { msg: unknown }).msg);
            return loc ? `${loc}: ${msg}` : msg;
          }
          return null;
        })
        .filter(Boolean);
      if (messages.length > 0) return messages.join(" · ");
    }

    // Forma { error, details: { campo: mensaje } }
    if (typeof obj.error === "string") {
      if (obj.details && typeof obj.details === "object") {
        const detailMessages = Object.entries(obj.details as Record<string, unknown>).map(
          ([field, msg]) => `${field}: ${msg}`
        );
        if (detailMessages.length > 0) return `${obj.error} — ${detailMessages.join(" · ")}`;
      }
      return obj.error;
    }

    if (typeof obj.message === "string") return obj.message;
  }

  return res.statusText || `Error ${res.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "No se pudo conectar con la API de Talent Tracker. Comprueba tu conexión e inténtalo de nuevo.",
      0
    );
  }

  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new ApiError(message, res.status);
  }

  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}

export const http = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
