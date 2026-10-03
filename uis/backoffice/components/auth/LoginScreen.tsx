"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FORGOT_PASSWORD_PATH } from "@/lib/auth";
import { toFormErrors } from "@/lib/authErrors";
import { ApiError } from "@/lib/http";
import { Spinner } from "./AuthGate";
import { useAuth } from "./AuthProvider";
import { AlertIcon, ArrowIcon, AuthShell, iconClasses, InfoIcon, inputClasses, MailIcon, PasswordInput } from "./AuthShell";

interface LoginScreenProps {
  /** Ruta interna a la que volver tras entrar (ya saneada por la página). */
  next: string;
  /** Por qué se llega al login: sesión caducada, cierre de sesión voluntario o contraseña restablecida. */
  reason: "caducada" | "salida" | "restablecida" | null;
}

const REASON_NOTICES = {
  caducada: {
    text: "Tu sesión ha caducado. Vuelve a iniciar sesión para continuar.",
    classes: "border-amber-200 bg-amber-50 text-amber-900",
  },
  salida: { text: "Has cerrado sesión correctamente.", classes: "border-blue-200 bg-blue-50 text-blue-900" },
  restablecida: {
    text: "Contraseña actualizada. Inicia sesión con tu nueva contraseña.",
    classes: "border-emerald-200 bg-emerald-50 text-emerald-900",
  },
} as const;

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) return "Revisa el email y la contraseña.";
  // 401 (credenciales), 403 (cuenta desactivada), sin conexión… ya llegan en español; lo desconocido se muestra igual.
  return toFormErrors(error, []).message ?? "Error inesperado. Inténtalo de nuevo.";
}

export function LoginScreen({ next, reason }: LoginScreenProps) {
  const { status, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  /** Seleccionar la contraseña tras el próximo render: durante el envío el input está deshabilitado y no admite foco. */
  const selectPassword = useRef(false);

  // Con una sesión válida (login correcto, otra pestaña, botón «atrás»…) no tiene sentido quedarse aquí.
  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  useEffect(() => {
    if (submitting || !selectPassword.current) return;
    passwordRef.current?.select();
    selectPassword.current = false;
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("Escribe tu email y tu contraseña.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      // La redirección la hace el efecto de arriba al pasar a `authenticated`.
    } catch (caught) {
      setError(loginErrorMessage(caught));
      setSubmitting(false);
      selectPassword.current = true;
    }
  }

  const busy = submitting || status === "authenticated";

  return (
    <AuthShell footnote="La sesión se guarda en este navegador y caduca automáticamente.">
      <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Acceso del equipo</p>
      <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">Inicia sesión</h1>
      <p className="mt-2 text-slate-600">Entra con tu cuenta de TrackFlow para usar el panel interno.</p>

      {reason && !error && (
        <p
          role="status"
          className={`mt-6 flex items-start gap-2.5 rounded-xl border p-3 text-sm ${REASON_NOTICES[reason].classes}`}
        >
          <InfoIcon className="mt-0.5 size-4 shrink-0" />
          {REASON_NOTICES[reason].text}
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800"
        >
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate className="mt-7 space-y-5">
        <div className="space-y-1.5">
          <label htmlFor="login-email" className="text-sm font-bold text-slate-700">
            Email
          </label>
          <div className="relative">
            <input
              id="login-email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoFocus
              required
              placeholder="nombre@trackflow.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={busy}
              aria-invalid={error ? true : undefined}
              className={`${inputClasses} pr-4`}
            />
            <MailIcon className={iconClasses} />
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="login-password" className="text-sm font-bold text-slate-700">
            Contraseña
          </label>
          <PasswordInput
            ref={passwordRef}
            id="login-password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
            disabled={busy}
            invalid={Boolean(error)}
          />
          {/* Tras el campo (y no junto a la etiqueta): con el teclado se pasa del email a la contraseña sin desvíos. */}
          <p className="text-right">
            <Link
              href={FORGOT_PASSWORD_PATH}
              className="text-sm font-semibold text-blue-700 underline-offset-2 hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
            >
              ¿Olvidaste tu contraseña?
            </Link>
          </p>
        </div>

        <button
          type="submit"
          disabled={busy}
          className="group flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:bg-blue-700/80"
        >
          {busy ? (
            <>
              <Spinner className="size-5" />
              Entrando…
            </>
          ) : (
            <>
              Entrar al backoffice
              <ArrowIcon className="size-4 transition group-hover:translate-x-0.5 motion-reduce:transition-none" />
            </>
          )}
        </button>
      </form>

      <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">
        ¿Todavía no tienes cuenta?{" "}
        <Link
          href={next === "/" ? "/register" : `/register?${new URLSearchParams({ next })}`}
          className="font-bold text-blue-700 underline-offset-2 hover:underline"
        >
          Crear cuenta
        </Link>
      </p>
    </AuthShell>
  );
}
