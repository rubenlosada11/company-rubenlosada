/**
 * Errores de la API en los formularios de cuenta (login, registro y perfil), en español.
 *
 * FastAPI/Pydantic devuelven algunos mensajes en inglés o con el nombre técnico del campo. Aquí se traducen los que
 * produce `services/api` (comprobados contra la API real); un mensaje desconocido se muestra tal cual, nunca se oculta.
 */
import { ApiError, FORM_ERROR } from "@/lib/http";

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
  "Field required": "Este campo es obligatorio.",
  "Input should be a valid string": "Debe ser un texto.",
  "Extra inputs are not permitted": "La API no admite este campo.",
  "email no tiene un formato válido": "El email no tiene un formato válido.",
  "phone no tiene un formato de teléfono válido": "El teléfono no tiene un formato válido (p. ej. +34 976 000 000).",
  "Envía al menos un campo: name, phone o address": "Cambia al menos un campo: nombre, teléfono o dirección.",
};

const PATTERNS: [RegExp, (match: RegExpMatchArray) => string][] = [
  [/^String should have at most (\d+) characters?$/, (m) => `Máximo ${m[1]} caracteres.`],
  [/^String should have at least (\d+) characters?$/, (m) => `Mínimo ${m[1]} caracteres.`],
];

/** Traduce un mensaje de la API; si no se conoce, lo devuelve igual (con punto final). */
export function translateApiMessage(message: string): string {
  const text = message.trim();
  if (EXACT[text]) return EXACT[text];
  for (const [pattern, build] of PATTERNS) {
    const match = text.match(pattern);
    if (match) return build(match);
  }
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
  if (!(error instanceof ApiError)) {
    const detail = error instanceof Error && error.message ? ` (${error.message})` : "";
    return { fields: {}, message: `Error inesperado${detail}. Inténtalo de nuevo.` };
  }

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
