"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { authApi, FORGOT_PASSWORD_PATH } from "@/lib/auth";
import { toFormErrors } from "@/lib/authErrors";
import { PASSWORD_MIN_LENGTH, passwordProblem } from "@/lib/authRules";
import { ApiError } from "@/lib/http";
import { Spinner } from "./AuthGate";
import { useAuth } from "./AuthProvider";
import { AlertIcon, ArrowIcon, AuthShell, FieldError, PasswordInput } from "./AuthShell";

interface ResetPasswordScreenProps {
  /** `?token=` del enlace del email, o `null` si falta. */
  token: string | null;
}

type FieldName = "new_password" | "confirm_password";

const FOOTNOTE = "El enlace caduca en poco tiempo y solo se puede usar una vez.";

/** Validación en el navegador: sin pasar estas reglas no se llama a la API. */
function validate(password: string, confirmation: string): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  if (!password) errors.new_password = "Elige una contraseña nueva.";
  else {
    const problem = passwordProblem(password);
    if (problem) errors.new_password = problem;
  }
  if (!confirmation) errors.confirm_password = "Repite la contraseña nueva.";
  else if (password && confirmation !== password) errors.confirm_password = "Las contraseñas no coinciden.";
  return errors;
}

/**
 * `/reset-password?token=…`: fija una contraseña nueva con el enlace del email (AUTH-03).
 *
 * Sin token no hay formulario. Si la API rechaza el enlace (400: no válido, caducado o ya usado), la pantalla lo dice y
 * ofrece pedir otro. Tras el cambio, la API cierra todas las sesiones del usuario: aquí también se borra la de este
 * navegador antes de ir al login.
 */
export function ResetPasswordScreen({ token }: ResetPasswordScreenProps) {
  const { logout } = useAuth();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [linkRejected, setLinkRejected] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const inFlight = useRef(false);
  /** Campo a enfocar tras el próximo render (durante el envío los inputs están deshabilitados y no aceptan foco). */
  const pendingFocus = useRef<FieldName | null>(null);

  useEffect(() => {
    if (submitting || !pendingFocus.current) return;
    formRef.current?.querySelector<HTMLInputElement>(`#reset-${pendingFocus.current}`)?.focus();
    pendingFocus.current = null;
  });

  function clearError(field: FieldName) {
    setFieldErrors((current) => {
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || inFlight.current) return;
    setFormError(null);

    const errors = validate(password, confirmation);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      const field: FieldName = errors.new_password ? "new_password" : "confirm_password";
      formRef.current?.querySelector<HTMLInputElement>(`#reset-${field}`)?.focus();
      return;
    }

    setFieldErrors({});
    inFlight.current = true;
    setSubmitting(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      // La API ya ha invalidado las sesiones anteriores; se borra también la de este navegador (y las demás pestañas
      // lo reciben por el evento `storage`). `replace`: el enlace con el token no queda en el historial.
      logout("logout");
      router.replace("/login?motivo=restablecida");
    } catch (caught) {
      inFlight.current = false;
      setSubmitting(false);
      if (caught instanceof ApiError && caught.status === 400) {
        setLinkRejected(true);
        return;
      }
      if (caught instanceof ApiError && caught.status === 422) {
        const { fields, message } = toFormErrors(caught, ["new_password"]);
        setFieldErrors(fields);
        setFormError(Object.keys(fields).length > 0 ? null : message);
        pendingFocus.current = "new_password";
        return;
      }
      setFormError(
        caught instanceof ApiError && caught.status === 0
          ? caught.message // sin conexión con la API (mensaje de lib/http.ts)
          : "No se ha podido cambiar la contraseña. Inténtalo de nuevo en unos minutos."
      );
    }
  }

  if (!token || linkRejected) {
    return (
      <AuthShell footnote={FOOTNOTE}>
        <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Restablecer contraseña</p>
        <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">
          {token ? "Este enlace ya no sirve" : "Falta el enlace"}
        </h1>
        <div
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          <p>
            {token
              ? "El enlace para restablecer la contraseña no es válido, ha caducado o ya se ha usado. Pide uno nuevo: llegará a tu email en unos minutos."
              : "Para restablecer la contraseña hay que abrir el enlace que te enviamos por email. Si no lo tienes o ha caducado, pide uno nuevo."}
          </p>
        </div>
        <Link
          href={FORGOT_PASSWORD_PATH}
          className="mt-7 flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          Volver a recuperar contraseña
          <ArrowIcon className="size-4" />
        </Link>
        <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">
          ¿La recuerdas?{" "}
          <Link href="/login" className="font-bold text-blue-700 underline-offset-2 hover:underline">
            Inicia sesión
          </Link>
        </p>
      </AuthShell>
    );
  }

  const busy = submitting || done;

  return (
    <AuthShell footnote={FOOTNOTE}>
      <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Restablecer contraseña</p>
      <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">Elige una contraseña nueva</h1>
      <p className="mt-2 text-slate-600">
        Al guardarla se cerrarán las sesiones abiertas de tu cuenta y podrás entrar con la nueva.
      </p>

      {formError && (
        <p
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800"
        >
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          {formError}
        </p>
      )}

      <form ref={formRef} onSubmit={handleSubmit} noValidate className="mt-7 space-y-5">
        <div className="space-y-1.5">
          <label htmlFor="reset-new_password" className="text-sm font-bold text-slate-700">
            Contraseña nueva
          </label>
          <PasswordInput
            id="reset-new_password"
            name="new_password"
            autoComplete="new-password"
            value={password}
            onChange={(value) => {
              setPassword(value);
              clearError("new_password");
            }}
            disabled={busy}
            invalid={Boolean(fieldErrors.new_password)}
            describedBy={fieldErrors.new_password ? "reset-new_password-hint reset-new_password-error" : "reset-new_password-hint"}
          />
          <p id="reset-new_password-hint" className="text-xs text-slate-500">
            Mínimo {PASSWORD_MIN_LENGTH} caracteres.
          </p>
          <FieldError id="reset-new_password-error" message={fieldErrors.new_password} />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reset-confirm_password" className="text-sm font-bold text-slate-700">
            Repite la contraseña nueva
          </label>
          <PasswordInput
            id="reset-confirm_password"
            name="confirm_password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(value) => {
              setConfirmation(value);
              clearError("confirm_password");
            }}
            disabled={busy}
            invalid={Boolean(fieldErrors.confirm_password)}
            describedBy={fieldErrors.confirm_password ? "reset-confirm_password-error" : undefined}
          />
          <FieldError id="reset-confirm_password-error" message={fieldErrors.confirm_password} />
        </div>

        <button
          type="submit"
          disabled={busy}
          className="group flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:bg-blue-700/80"
        >
          {busy ? (
            <>
              <Spinner className="size-5" />
              Guardando…
            </>
          ) : (
            <>
              Guardar contraseña
              <ArrowIcon className="size-4 transition group-hover:translate-x-0.5 motion-reduce:transition-none" />
            </>
          )}
        </button>
      </form>

      <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">
        ¿Te ha caducado el enlace?{" "}
        <Link href={FORGOT_PASSWORD_PATH} className="font-bold text-blue-700 underline-offset-2 hover:underline">
          Pide otro
        </Link>
      </p>
    </AuthShell>
  );
}
