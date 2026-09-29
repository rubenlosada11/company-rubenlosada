"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/http";
import { useAuth } from "./AuthProvider";
import { Spinner } from "./AuthGate";

interface LoginScreenProps {
  /** Ruta interna a la que volver tras entrar (ya saneada por la página). */
  next: string;
  /** Por qué se llega al login: sesión caducada o cierre de sesión voluntario. */
  reason: "caducada" | "salida" | null;
}

const MODULES = [
  { title: "Directorio de proveedores", text: "Carriers, embalaje y software de USA y España." },
  { title: "Análisis de incidencias", text: "Métricas del CSV de atención al cliente." },
  { title: "Iniciativas e hitos", text: "Las necesidades de cada área del negocio." },
];

const inputClasses =
  "peer w-full rounded-xl border border-slate-300 bg-white py-3 pl-11 text-[15px] text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100 focus:outline-none aria-invalid:border-red-400 aria-invalid:focus:ring-red-100 disabled:bg-slate-50";

function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Error inesperado. Inténtalo de nuevo.";
  if (error.status === 422) return "Revisa el email y la contraseña.";
  return error.message;
}

export function LoginScreen({ next, reason }: LoginScreenProps) {
  const { status, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Con una sesión válida (otra pestaña del login, botón «atrás»…) no tiene sentido quedarse aquí.
  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

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
      passwordRef.current?.select();
    }
  }

  const busy = submitting || status === "authenticated";

  return (
    <div className="min-h-screen bg-slate-100 lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <BrandPanel />

      <main id="contenido" className="flex min-h-screen items-center justify-center px-4 py-10 sm:px-6 lg:min-h-0">
        <div className="animate-fade-up w-full max-w-md motion-reduce:animate-none">
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <Image
              src="/logo/TrackFlow_Logo1_Full.png"
              alt="Logo de TrackFlow"
              width={1190}
              height={264}
              priority
              className="h-8 w-auto"
            />
            <span className="rounded-full bg-blue-700 px-2.5 py-0.5 text-xs font-bold tracking-wide text-white uppercase">
              Backoffice
            </span>
          </div>

          <div className="rounded-3xl bg-white p-6 shadow-xl ring-1 shadow-blue-950/5 ring-slate-200 sm:p-9">
            <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Acceso del equipo</p>
            <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">Inicia sesión</h1>
            <p className="mt-2 text-slate-600">Entra con tu cuenta de TrackFlow para usar el panel interno.</p>

            {reason && !error && (
              <p
                role="status"
                className={`mt-6 flex items-start gap-2.5 rounded-xl border p-3 text-sm ${
                  reason === "caducada"
                    ? "border-amber-200 bg-amber-50 text-amber-900"
                    : "border-blue-200 bg-blue-50 text-blue-900"
                }`}
              >
                <InfoIcon className="mt-0.5 size-4 shrink-0" />
                {reason === "caducada"
                  ? "Tu sesión ha caducado. Vuelve a iniciar sesión para continuar."
                  : "Has cerrado sesión correctamente."}
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
                  <MailIcon className="pointer-events-none absolute top-1/2 left-4 size-[18px] -translate-y-1/2 text-slate-400 transition peer-focus:text-blue-700" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="login-password" className="text-sm font-bold text-slate-700">
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    ref={passwordRef}
                    id="login-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    placeholder="••••••••"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={busy}
                    aria-invalid={error ? true : undefined}
                    className={`${inputClasses} pr-12`}
                  />
                  <LockIcon className="pointer-events-none absolute top-1/2 left-4 size-[18px] -translate-y-1/2 text-slate-400 transition peer-focus:text-blue-700" />
                  <button
                    type="button"
                    onClick={() => setShowPassword((shown) => !shown)}
                    aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    aria-pressed={showPassword}
                    aria-controls="login-password"
                    className="absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-2 focus-visible:outline-blue-700"
                  >
                    {showPassword ? <EyeOffIcon className="size-[18px]" /> : <EyeIcon className="size-[18px]" />}
                  </button>
                </div>
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
              ¿Todavía no tienes acceso? Pide a un administrador de TrackFlow que te dé de alta.
            </p>
          </div>

          <p className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
            <ShieldIcon className="size-3.5" />
            La sesión se guarda solo en esta pestaña y caduca automáticamente.
          </p>
        </div>
      </main>
    </div>
  );
}

function BrandPanel() {
  return (
    <aside className="relative hidden overflow-hidden bg-blue-950 text-blue-100 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:gap-10 lg:p-12 xl:px-16">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 -left-32 size-[30rem] rounded-full bg-blue-600/30 blur-3xl" />
        <div className="absolute -right-24 -bottom-48 size-[34rem] rounded-full bg-sky-400/15 blur-3xl" />
        <div className="absolute inset-0 [background-image:linear-gradient(to_right,rgb(255_255_255/0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/0.05)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_75%)]" />
      </div>

      <div className="relative">
        <div className="inline-flex rounded-2xl bg-white px-4 py-3 shadow-lg shadow-blue-950/40">
          <Image
            src="/logo/TrackFlow_Logo1_Full.png"
            alt="Logo de TrackFlow"
            width={1190}
            height={264}
            priority
            className="h-8 w-auto"
          />
        </div>
      </div>

      <div className="relative max-w-xl">
        <p className="text-xs font-bold tracking-[0.17em] text-blue-300 uppercase">Backoffice · Uso interno</p>
        <h2 className="mt-4 font-heading text-4xl leading-[1.1] font-bold tracking-tight text-white xl:text-[2.75rem]">
          La operación de TrackFlow, en un solo panel.
        </h2>
        <p className="mt-4 max-w-lg text-lg leading-relaxed text-blue-200">
          De Los Ángeles a Zaragoza: proveedores, incidencias y proyectos del equipo, con acceso protegido por tu
          cuenta.
        </p>

        <RouteCard />

        <ul className="mt-6 grid gap-3 xl:grid-cols-3">
          {MODULES.map((module) => (
            <li key={module.title} className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
              <p className="font-heading text-sm font-bold text-white">{module.title}</p>
              <p className="mt-1 text-sm leading-snug text-blue-200">{module.text}</p>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative text-xs text-blue-300">TrackFlow Tech · Acceso restringido al equipo de TrackFlow.</p>
    </aside>
  );
}

/** Ruta decorativa entre los dos almacenes de TrackFlow (CONTEXT.es.md). */
function RouteCard() {
  return (
    <div className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
      <svg viewBox="0 0 400 90" className="h-auto w-full" role="img" aria-label="Ruta entre los almacenes de Los Ángeles y Zaragoza">
        <path
          d="M 24 62 C 120 -6, 280 -6, 376 62"
          fill="none"
          stroke="rgb(147 197 253 / 0.25)"
          strokeWidth="2"
        />
        <path
          d="M 24 62 C 120 -6, 280 -6, 376 62"
          fill="none"
          stroke="rgb(147 197 253)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="6 14"
          className="animate-route motion-reduce:animate-none"
        />
        {[24, 376].map((cx) => (
          <g key={cx}>
            <circle cx={cx} cy="62" r="12" fill="rgb(59 130 246 / 0.25)" className="animate-pulse motion-reduce:animate-none" />
            <circle cx={cx} cy="62" r="5.5" fill="white" />
          </g>
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-sm">
        <span>
          <span className="block font-bold text-white">Los Ángeles</span>
          <span className="text-blue-300">Almacén · USA</span>
        </span>
        <span className="text-right">
          <span className="block font-bold text-white">Zaragoza</span>
          <span className="text-blue-300">Almacén · España</span>
        </span>
      </div>
    </div>
  );
}

type IconProps = { className?: string };

function Icon({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

const MailIcon = (props: IconProps) => (
  <Icon {...props}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </Icon>
);

const LockIcon = (props: IconProps) => (
  <Icon {...props}>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </Icon>
);

const EyeIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
);

const EyeOffIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M10.6 5.1A10.7 10.7 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.2M6.6 6.6A17.4 17.4 0 0 0 2 12s3.5 7 10 7a9.9 9.9 0 0 0 5.4-1.6" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18" />
  </Icon>
);

const ArrowIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
);

const AlertIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5M12 16.5v.01" />
  </Icon>
);

const InfoIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.01" />
  </Icon>
);

const ShieldIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3Z" />
  </Icon>
);
