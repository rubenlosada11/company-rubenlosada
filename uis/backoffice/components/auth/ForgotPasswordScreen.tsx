"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authApi, FORGOT_PASSWORD_MESSAGE } from "@/lib/auth";
import { EMAIL_PATTERN } from "@/lib/authRules";
import { ApiError } from "@/lib/http";
import { Spinner } from "./AuthGate";
import { AlertIcon, ArrowIcon, AuthShell, FieldError, iconClasses, inputClasses, MailIcon } from "./AuthShell";

const FOOTNOTE = "Por seguridad, nunca indicamos si un email tiene cuenta en TrackFlow.";

/**
 * `/forgot-password`: pide el enlace para restablecer la contraseña (AUTH-03).
 *
 * Tras enviar se muestra siempre el mismo mensaje, exista o no la cuenta: el texto es fijo y no depende de la API. Solo
 * los errores de formato o de conexión se muestran como error, y ninguno dice nada sobre el email.
 */
export function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const sentHeadingRef = useRef<HTMLHeadingElement>(null);
  /** Evita un segundo envío aunque llegue antes de que React deshabilite el botón (doble clic muy rápido). */
  const inFlight = useRef(false);
  /** Enfocar el email tras el próximo render: durante el envío el input está deshabilitado y no admite foco. */
  const focusEmail = useRef(false);

  useEffect(() => {
    if (sent) sentHeadingRef.current?.focus();
  }, [sent]);

  useEffect(() => {
    if (submitting || !focusEmail.current) return;
    inputRef.current?.focus();
    focusEmail.current = false;
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setFormError(null);

    const value = email.trim();
    const problem = !value ? "Escribe tu email." : EMAIL_PATTERN.test(value) ? null : "El email no tiene un formato válido.";
    if (problem) {
      setFieldError(problem);
      inputRef.current?.focus();
      return;
    }

    setFieldError(null);
    inFlight.current = true;
    setSubmitting(true);
    try {
      await authApi.forgotPassword(value);
      setSent(true);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422) {
        setFieldError("El email no tiene un formato válido.");
      } else if (caught instanceof ApiError && caught.status === 0) {
        setFormError(caught.message); // sin conexión con la API (mensaje de lib/http.ts)
      } else {
        setFormError("No se ha podido enviar la solicitud. Inténtalo de nuevo en unos minutos.");
      }
      focusEmail.current = true;
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <AuthShell footnote={FOOTNOTE}>
        <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Recuperar acceso</p>
        <h1
          ref={sentHeadingRef}
          tabIndex={-1}
          className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900 focus:outline-none"
        >
          Revisa tu correo
        </h1>
        <div
          role="status"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"
        >
          <MailIcon className="mt-0.5 size-4 shrink-0" />
          <p className="font-semibold">{FORGOT_PASSWORD_MESSAGE}</p>
        </div>
        <p className="mt-4 text-sm text-slate-600">
          El enlace caduca en poco tiempo y solo se puede usar una vez. Si no lo ves en unos minutos, revisa la carpeta
          de spam.
        </p>
        <Link
          href="/login"
          className="mt-7 flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          Volver a iniciar sesión
          <ArrowIcon className="size-4" />
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell footnote={FOOTNOTE}>
      <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Recuperar acceso</p>
      <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">¿Olvidaste tu contraseña?</h1>
      <p className="mt-2 text-slate-600">
        Escribe el email de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
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

      <form onSubmit={handleSubmit} noValidate className="mt-7 space-y-5">
        <div className="space-y-1.5">
          <label htmlFor="forgot-email" className="text-sm font-bold text-slate-700">
            Email
          </label>
          <div className="relative">
            <input
              ref={inputRef}
              id="forgot-email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoFocus
              required
              placeholder="nombre@trackflow.com"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setFieldError(null);
              }}
              disabled={submitting}
              aria-invalid={fieldError ? true : undefined}
              aria-describedby={fieldError ? "forgot-email-error" : undefined}
              className={`${inputClasses} pr-4`}
            />
            <MailIcon className={iconClasses} />
          </div>
          <FieldError id="forgot-email-error" message={fieldError ?? undefined} />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="group flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:bg-blue-700/80"
        >
          {submitting ? (
            <>
              <Spinner className="size-5" />
              Enviando…
            </>
          ) : (
            <>
              Enviar enlace
              <ArrowIcon className="size-4 transition group-hover:translate-x-0.5 motion-reduce:transition-none" />
            </>
          )}
        </button>
      </form>

      <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">
        ¿La recuerdas?{" "}
        <Link href="/login" className="font-bold text-blue-700 underline-offset-2 hover:underline">
          Inicia sesión
        </Link>
      </p>
    </AuthShell>
  );
}
