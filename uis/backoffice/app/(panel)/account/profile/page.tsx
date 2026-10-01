import type { Metadata } from "next";
import { ProfileEditor } from "@/components/auth/ProfileEditor";

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
    </div>
  );
}
