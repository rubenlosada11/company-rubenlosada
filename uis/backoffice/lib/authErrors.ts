/**
 * Errores de la API en los formularios de cuenta (login, registro y perfil), en español.
 *
 * `lib/http.ts` ya traduce los mensajes de Pydantic (en inglés). Aquí se pulen los que redacta `services/api` con el
 * nombre técnico del campo (comprobados contra la API real); el resto de mensajes de la API se muestra tal cual.
 */
import { ApiError, FORM_ERROR, SERVER_ERROR_MESSAGE, SESSION_EXPIRED_MESSAGE } from "@/lib/http";

export const FIELD_LABELS: Record<string, string> = {
  email: "Email",
  password: "Contraseña",
  name: "Nombre",
  phone: "Teléfono",
  address: "Dirección",
  invitation_code: "Código de invitación",
  new_password: "Contraseña nueva",
  current_password: "Contraseña actual",
  token: "Enlace",
};

const EXACT: Record<string, string> = {
  // 401 de una petición protegida (p. ej. `/auth/me` justo después de entrar): la API habla de tokens y cabeceras.
  "No autenticado. Inicia sesión y envía el token en la cabecera Authorization: Bearer <token>.": SESSION_EXPIRED_MESSAGE,
  "Token no válido.": SESSION_EXPIRED_MESSAGE,
  "El token ha caducado. Inicia sesión de nuevo.": SESSION_EXPIRED_MESSAGE,
  "email no tiene un formato válido": "El email no tiene un formato válido.",
  "phone no tiene un formato de teléfono válido": "El teléfono no tiene un formato válido (p. ej. +34 976 000 000).",
  "Envía al menos un campo: name, phone o address": "Cambia al menos un campo: nombre, teléfono o dirección.",
};

/** Pule un mensaje de la API; si no está en la tabla, lo devuelve igual (con punto final). */
export function translateApiMessage(message: string): string {
  const text = message.trim();
  if (EXACT[text]) return EXACT[text];
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export interface FormErrors {
  /** Error por campo del formulario (clave = nombre del campo en la API). */
  fields: Record<string, string>;
  /** Mensaje general para el aviso del formulario, o `null` si basta con los errores por campo. */
  message: string | null;
}

/**
 * Reparte un error de la API entre los campos visibles del formulario y un mensaje general. Los errores de campos que
 * el formulario no muestra se añaden al mensaje general con su etiqueta, para que no se pierdan.
 */
export function toFormErrors(error: unknown, visibleFields: readonly string[]): FormErrors {
  // El mensaje de un error que no viene de la API es técnico (p. ej. un `TypeError`): no se muestra.
  if (!(error instanceof ApiError)) return { fields: {}, message: "Error inesperado. Inténtalo de nuevo." };
  if (error.status >= 500) return { fields: {}, message: SERVER_ERROR_MESSAGE };

  const entries = Object.entries(error.fieldErrors);
  if (entries.length === 0) return { fields: {}, message: translateApiMessage(error.message) };

  const fields: Record<string, string> = {};
  const loose: string[] = [];
  for (const [field, raw] of entries) {
    const message = translateApiMessage(raw);
    if (visibleFields.includes(field)) fields[field] = message;
    else if (field === FORM_ERROR) loose.push(message);
    else loose.push(`${FIELD_LABELS[field] ?? field}: ${message}`);
  }
  const message = loose.length > 0 ? loose.join(" ") : "Revisa los campos marcados.";
  return { fields, message };
}
