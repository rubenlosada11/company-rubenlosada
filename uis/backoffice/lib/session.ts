/**
 * Token de acceso del backoffice (JWT de `services/api`).
 *
 * Se guarda en `localStorage` (requisito de AUTH-02): sobrevive a recargas y a cerrar el navegador, se comparte entre
 * las pestañas del mismo origen y no se envía solo a ningún servidor (la API autentica únicamente con la cabecera
 * `Authorization: Bearer`, sin cookies). Su vida la limita el `exp` del JWT. Solo se lee en el navegador (efectos y
 * eventos), nunca durante el render en el servidor. Módulo sin React para que `lib/http.ts` lo use.
 */
export const TOKEN_KEY = "trackflow.backoffice.token";

/** Evento que emite `lib/http.ts` cuando la API responde 401 a una petición autenticada (token caducado o revocado). */
export const UNAUTHORIZED_EVENT = "trackflow:unauthorized";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Guarda el token y devuelve si se pudo: con el almacenamiento bloqueado (modo privado estricto) no hay sesión. */
export function saveToken(token: string): boolean {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    return true;
  } catch {
    return false;
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
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
  // Las pantallas de acceso no son destinos: volver a ellas ya con sesión no tiene sentido (y `/reset-password`
  // llevaría un token en la URL).
  const accessScreen = /^\/(login|register|forgot-password|reset-password)(?![^/?#])/;
  if (!value || !value.startsWith("/") || /^\/[/\\]/.test(value) || accessScreen.test(value)) {
    return "/";
  }
  return value;
}
