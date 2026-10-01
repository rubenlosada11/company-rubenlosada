import type { Metadata } from "next";
import Link from "next/link";
import { ProfileEditor } from "@/components/auth/ProfileEditor";
import { CHANGE_PASSWORD_PATH } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Mi perfil | TrackFlow Tech",
  description: "Datos de tu cuenta y de contacto en el backoffice de TrackFlow Tech.",
};

/** Perfil del usuario conectado. Privada: está dentro de `app/(panel)/`, protegida por `AuthGate`. */
export default function ProfilePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">TrackFlow Tech · Tu cuenta</p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">Mi perfil</h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Tu email y tu rol identifican tu cuenta. Puedes mantener al día tu nombre, teléfono y dirección de contacto.
        </p>
      </header>

      <ProfileEditor />

      <section aria-labelledby="seguridad-title" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 id="seguridad-title" className="font-heading text-xl tracking-tight text-slate-900">
          Seguridad
        </h2>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-md text-sm text-slate-600">
            Cambia tu contraseña. Se cerrarán las sesiones abiertas en otros navegadores y dispositivos.
          </p>
          <Link
            href={CHANGE_PASSWORD_PATH}
            className="inline-flex items-center rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-bold text-slate-800 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            Cambiar contraseña
          </Link>
        </div>
      </section>
    </div>
  );
}
