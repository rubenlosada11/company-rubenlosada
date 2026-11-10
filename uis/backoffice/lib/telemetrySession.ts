/**
 * Identificadores de correlación de la telemetría (plan §8.2 y §8.3). Sin React, para que lo usen `lib/http.ts`,
 * `lib/telemetry.ts` y el `AuthProvider`.
 *
 * - `sessionId`: la sesión **autenticada** del backoffice. Se genera justo antes de enviar el login (viaja en la cabecera
 *   `X-Session-Id` del propio login), se confirma si el login va bien y se borra al cerrar la sesión. Se guarda junto al
 *   token en `localStorage` porque tiene su misma vida: sobrevive a recargas y lo comparten las pestañas, igual que la
 *   sesión a la que pertenece. Nunca se deriva del token.
 * - `requestId`: un UUID v4 por petición a la API (cabecera `X-Request-Id`; la API lo devuelve y lo usa en sus eventos y
 *   logs). Los formularios reservan el suyo para poder unir `form_submitted` con el evento de negocio de la API.
 */

export const TELEMETRY_SESSION_KEY = "trackflow.backoffice.telemetry_session";

interface StoredSession {
  id: string;
  /** Inicio de la sesión (epoch en ms), para `session_duration_seconds`. */
  startedAt: number;
}

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** UUID v4 en minúsculas. `crypto.randomUUID` solo existe en contextos seguros (https y localhost). */
export function newUuid(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") return cryptoApi.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === "function") cryptoApi.getRandomValues(bytes);
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function isUuidV4(value: unknown): value is string {
  return typeof value === "string" && UUID_V4.test(value);
}

/** Sesión del login en curso: existe desde que se envía el login hasta que se confirma o se descarta. */
let pending: StoredSession | null = null;

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readStored(): StoredSession | null {
  try {
    const raw = storage()?.getItem(TELEMETRY_SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredSession>;
    return isUuidV4(value.id) && typeof value.startedAt === "number" ? { id: value.id, startedAt: value.startedAt } : null;
  } catch {
    return null;
  }
}

/** Genera el `sessionId` de un login que va a enviarse. Devuelve el id para la cabecera `X-Session-Id`. */
export function beginTelemetrySession(): string {
  pending = { id: newUuid(), startedAt: Date.now() };
  return pending.id;
}

/** El login ha ido bien: la sesión pendiente pasa a ser la sesión actual (compartida con las demás pestañas). */
export function commitTelemetrySession(): void {
  if (!pending) return;
  try {
    storage()?.setItem(TELEMETRY_SESSION_KEY, JSON.stringify(pending));
  } catch {
    // Almacenamiento bloqueado: sin token tampoco hay sesión; el login ya lo avisa.
  }
  pending = null;
}

/** El login ha fallado: no hay sesión (`login_failed` y la telemetría de la pantalla de login van sin `sessionId`). */
export function discardPendingTelemetrySession(): void {
  pending = null;
}

/**
 * Hay sesión autenticada pero no `sessionId` (p. ej. un token guardado antes de existir la telemetría): se crea uno
 * nuevo, que cuenta como el inicio de la sesión para la telemetría.
 */
export function ensureTelemetrySession(): void {
  if (readStored()) return;
  try {
    storage()?.setItem(TELEMETRY_SESSION_KEY, JSON.stringify({ id: newUuid(), startedAt: Date.now() }));
  } catch {
    // Sin almacenamiento no hay sesión que guardar.
  }
}

/** `sessionId` para el envelope y la cabecera `X-Session-Id`: la sesión actual o, durante el login, la pendiente. */
export function currentTelemetrySessionId(): string | null {
  return readStored()?.id ?? pending?.id ?? null;
}

/** Sesión actual con su inicio, o `null` (ya cerrada, quizá por otra pestaña). */
export function currentTelemetrySession(): StoredSession | null {
  return readStored();
}

export function clearTelemetrySession(): void {
  try {
    storage()?.removeItem(TELEMETRY_SESSION_KEY);
  } catch {
    // Nada que borrar.
  }
}

// --- requestId de los formularios -----------------------------------------------------------------------------

const formRequests = new Map<string, string>();

/** Id de la petición que va a hacer un formulario (lo pasa a la llamada de la API como `requestId`). */
export function reserveFormRequestId(formId: string): string {
  const id = newUuid();
  formRequests.set(formId, id);
  return id;
}

/** Lo usa el envelope de `form_submitted`: el id de la última petición de ese formulario (una sola vez). */
export function takeFormRequestId(formId: string): string | null {
  const id = formRequests.get(formId) ?? null;
  formRequests.delete(formId);
  return id;
}
