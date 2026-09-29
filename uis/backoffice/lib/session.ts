/**
 * Token de acceso del backoffice (JWT de `services/api`).
 *
 * Se guarda en `sessionStorage`: dura lo que la pestaña y no se envía solo a ningún servidor (la API autentica
 * únicamente con la cabecera `Authorization: Bearer`, sin cookies). Módulo sin React para que `lib/http.ts` lo use.
 */
const TOKEN_KEY = "trackflow.backoffice.token";

/** Evento que emite `lib/http.ts` cuando la API responde 401 a una petición con token (caducado o revocado). */
export const UNAUTHORIZED_EVENT = "trackflow:unauthorized";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string): void {
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Almacenamiento bloqueado (modo privado estricto): la sesión dura hasta recargar la página.
  }
}

export function clearToken(): void {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nada que limpiar.
  }
}

/**
 * Milisegundos (epoch) en que caduca el token según su claim `exp`, o `null` si no se puede leer.
 * Solo sirve para no usar un token ya caducado y cerrar la sesión a tiempo: la API es quien valida la firma.
 */
export function tokenExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(payload.length / 4) * 4, "="));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Ruta interna segura a la que volver tras el login (evita redirecciones abiertas como `//otro-dominio`). */
export function safeNextPath(value: string | null): string {
  // `/\` también es una URL a otro dominio para los navegadores.
  if (!value || !value.startsWith("/") || /^\/[/\\]/.test(value) || value.startsWith("/login")) return "/";
  return value;
}
