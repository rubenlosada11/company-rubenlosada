"use client";

import { useEffect, useRef, useState } from "react";
import { toFormErrors } from "@/lib/authErrors";
import { PASSWORD_MIN_LENGTH, passwordProblem } from "@/lib/authRules";
import { ApiError } from "@/lib/http";
import { Spinner } from "./AuthGate";
import { useAuth } from "./AuthProvider";
import { AlertIcon, FieldError, PasswordInput } from "./AuthShell";

type FieldName = "current_password" | "new_password" | "confirm_password";
type Values = Record<FieldName, string>;

const EMPTY: Values = { current_password: "", new_password: "", confirm_password: "" };
const FIELDS: readonly FieldName[] = ["current_password", "new_password", "confirm_password"];
const LABELS: Record<FieldName, string> = {
  current_password: "Contraseña actual",
  new_password: "Contraseña nueva",
  confirm_password: "Repite la contraseña nueva",
};

/** Validación en el navegador: sin pasar estas reglas no se llama a la API. */
function validate(values: Values): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  if (!values.current_password) errors.current_password = "Escribe tu contraseña actual.";
  if (!values.new_password) errors.new_password = "Elige una contraseña nueva.";
  else {
    const problem = passwordProblem(values.new_password);
    if (problem) errors.new_password = problem;
    else if (values.new_password === values.current_password)
      errors.new_password = "La contraseña nueva debe ser distinta de la actual.";
  }
  if (!values.confirm_password) errors.confirm_password = "Repite la contraseña nueva.";
  else if (values.new_password && values.confirm_password !== values.new_password)
    errors.confirm_password = "Las contraseñas no coinciden.";
  return errors;
}

/**
 * `/account/change-password`: cambia la contraseña del usuario conectado con `POST /auth/change-password` (AUTH-03).
 *
 * Distingue contraseña actual incorrecta (400, en su campo), contraseña nueva no válida (422), sesión no válida (401: lo
 * gestiona `lib/http.ts`, que cierra la sesión y vuelve al login) y errores inesperados. Tras el cambio, `AuthProvider`
 * guarda el token nuevo: esta sesión sigue abierta y las demás quedan cerradas.
 */
export function ChangePasswordForm() {
  const { changePassword } = useAuth();
  const [values, setValues] = useState<Values>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const successRef = useRef<HTMLParagraphElement>(null);
  const inFlight = useRef(false);
  /** Campo a enfocar tras el próximo render (mientras se guarda, los inputs están deshabilitados). */
  const pendingFocus = useRef<FieldName | null>(null);

  useEffect(() => {
    if (saving || !pendingFocus.current) return;
    formRef.current?.querySelector<HTMLInputElement>(`#change-${pendingFocus.current}`)?.focus();
    pendingFocus.current = null;
  });

  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  function update(field: FieldName, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSuccess(false);
    setFieldErrors((current) => {
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setFormError(null);
    setSuccess(false);

    const errors = validate(values);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      const first = FIELDS.find((field) => errors[field]);
      formRef.current?.querySelector<HTMLInputElement>(`#change-${first}`)?.focus();
      return;
    }

    setFieldErrors({});
    inFlight.current = true;
    setSaving(true);
    try {
      await changePassword(values.current_password, values.new_password);
      setValues(EMPTY);
      setSuccess(true);
    } catch (caught) {
      // 401: `lib/http.ts` ya ha cerrado la sesión y `AuthGate` lleva al login; no hay nada que mostrar aquí.
      if (caught instanceof ApiError && caught.status === 401) return;
      if (caught instanceof ApiError && caught.status === 400) {
        setFieldErrors({ current_password: "La contraseña actual no es correcta." });
        pendingFocus.current = "current_password";
      } else if (caught instanceof ApiError && caught.status === 422) {
        const { fields, message } = toFormErrors(caught, ["current_password", "new_password"]);
        setFieldErrors(fields);
        setFormError(Object.keys(fields).length > 0 ? null : message);
        pendingFocus.current = fields.current_password ? "current_password" : "new_password";
      } else {
        setFormError(
          caught instanceof ApiError && caught.status === 0
            ? caught.message // sin conexión con la API (mensaje de lib/http.ts)
            : "No se ha podido cambiar la contraseña. Inténtalo de nuevo en unos minutos."
        );
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="password-title" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <h2 id="password-title" className="font-heading text-xl tracking-tight text-slate-900">
        Contraseña
      </h2>
      <p className="mt-1.5 text-sm text-slate-600">
        Al cambiarla se cerrarán las sesiones abiertas en otros navegadores y dispositivos. Esta seguirá abierta.
      </p>

      {formError && (
        <p
          role="alert"
          className="mt-5 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800"
        >
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          {formError}
        </p>
      )}

      {success && (
        <p
          ref={successRef}
          tabIndex={-1}
          role="status"
          className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-semibold text-emerald-800 focus:outline-none"
        >
          Contraseña actualizada. Hemos cerrado las demás sesiones abiertas de tu cuenta.
        </p>
      )}

      <form ref={formRef} onSubmit={handleSubmit} noValidate className="mt-6 max-w-md space-y-5">
        {FIELDS.map((field) => {
          const inputId = `change-${field}`;
          const hint = field === "new_password" ? `${inputId}-hint` : null;
          const error = fieldErrors[field];
          const describedBy = [hint, error && `${inputId}-error`].filter(Boolean).join(" ") || undefined;
          return (
            <div key={field} className="space-y-1.5">
              <label htmlFor={inputId} className="text-sm font-bold text-slate-700">
                {LABELS[field]}
              </label>
              <PasswordInput
                id={inputId}
                name={field}
                autoComplete={field === "current_password" ? "current-password" : "new-password"}
                value={values[field]}
                onChange={(value) => update(field, value)}
                disabled={saving}
                invalid={Boolean(error)}
                describedBy={describedBy}
              />
              {hint && (
                <p id={hint} className="text-xs text-slate-500">
                  Mínimo {PASSWORD_MIN_LENGTH} caracteres y distinta de la actual.
                </p>
              )}
              <FieldError id={`${inputId}-error`} message={error} />
            </div>
          );
        })}

        <div className="pt-1">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:bg-blue-700/80"
          >
            {saving ? (
              <>
                <Spinner className="size-4" />
                Guardando…
              </>
            ) : (
              "Cambiar contraseña"
            )}
          </button>
        </div>
      </form>
    </section>
  );
}
