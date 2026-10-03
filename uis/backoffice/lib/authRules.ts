/**
 * Reglas de los formularios de cuenta, iguales que las de `services/api/app/auth_models.py`. Se comprueban en el
 * navegador para avisar sin llamar a la API; la API vuelve a validarlo todo.
 */
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const PASSWORD_MIN_LENGTH = 8;
/** bcrypt solo usa 72 bytes: las tildes y la ñ ocupan 2. */
export const PASSWORD_MAX_BYTES = 72;

/** Problema de longitud de una contraseña nueva (no vacía), o `null` si cumple las reglas. */
export function passwordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres.`;
  if (new TextEncoder().encode(password).length > PASSWORD_MAX_BYTES)
    return "La contraseña es demasiado larga (máximo 72 bytes; las tildes y la ñ ocupan 2).";
  return null;
}
