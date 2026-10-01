"use client";

import Image from "next/image";
import { useState } from "react";

/**
 * Piezas comunes de las pantallas públicas del backoffice (`/login` y `/register`): layout a pantalla completa con el
 * panel de marca, campo de contraseña con mostrar/ocultar, clases de los inputs e iconos.
 */

const MODULES = [
  { title: "Directorio de proveedores", text: "Carriers, embalaje y software de USA y España." },
  { title: "Análisis de incidencias", text: "Métricas del CSV de atención al cliente." },
  { title: "Iniciativas e hitos", text: "Las necesidades de cada área del negocio." },
];

export const inputClasses =
  "peer w-full rounded-xl border border-slate-300 bg-white py-3 pl-11 text-[15px] text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100 focus:outline-none aria-invalid:border-red-400 aria-invalid:focus:ring-red-100 disabled:bg-slate-50";

export const iconClasses =
  "pointer-events-none absolute top-1/2 left-4 size-[18px] -translate-y-1/2 text-slate-400 transition peer-focus:text-blue-700";

interface AuthShellProps {
  /** Contenido de la tarjeta (título, avisos y formulario). */
  children: React.ReactNode;
  /** Nota bajo la tarjeta. */
  footnote: React.ReactNode;
}

export function AuthShell({ children, footnote }: AuthShellProps) {
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
            {children}
          </div>

          {/* Icono en línea con el texto: si la nota ocupa dos líneas (móvil), el escudo acompaña a la primera. */}
          <p className="mt-6 text-center text-xs text-slate-500">
            <ShieldIcon className="mr-1.5 inline size-3.5 align-[-2px]" />
            {footnote}
          </p>
        </div>
      </main>
    </div>
  );
}

interface PasswordInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  ref?: React.Ref<HTMLInputElement>;
}

/** Campo de contraseña con icono y botón de mostrar/ocultar. */
export function PasswordInput({ id, value, onChange, autoComplete, disabled, invalid, describedBy, ref }: PasswordInputProps) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <input
        ref={ref}
        id={id}
        name="password"
        type={shown ? "text" : "password"}
        autoComplete={autoComplete}
        required
        placeholder="••••••••"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        className={`${inputClasses} pr-12`}
      />
      <LockIcon className={iconClasses} />
      <button
        type="button"
        onClick={() => setShown((current) => !current)}
        aria-label={shown ? "Ocultar contraseña" : "Mostrar contraseña"}
        aria-pressed={shown}
        aria-controls={id}
        className="absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-2 focus-visible:outline-blue-700"
      >
        {shown ? <EyeOffIcon className="size-[18px]" /> : <EyeIcon className="size-[18px]" />}
      </button>
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

export const MailIcon = (props: IconProps) => (
  <Icon {...props}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </Icon>
);

export const LockIcon = (props: IconProps) => (
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

export const ArrowIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
);

export const AlertIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5M12 16.5v.01" />
  </Icon>
);

export const InfoIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.01" />
  </Icon>
);

export const UserIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Icon>
);

export const PhoneIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />
  </Icon>
);

export const PinIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12Z" />
    <circle cx="12" cy="9" r="2.5" />
  </Icon>
);

export const KeyIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="7.5" cy="15.5" r="4.5" />
    <path d="m10.7 12.3 9.3-9.3M16 7l3 3M14 9l2 2" />
  </Icon>
);

const ShieldIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3Z" />
  </Icon>
);
