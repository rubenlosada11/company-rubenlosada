import type { Metadata } from "next";
import Link from "next/link";
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { PROFILE_PATH } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Cambiar contraseña | TrackFlow Tech",
  description: "Cambia la contraseña de tu cuenta del backoffice de TrackFlow Tech.",
};

/** Cambio de contraseña del usuario conectado. Privada: está dentro de `app/(panel)/`, protegida por `AuthGate`. */
export default function ChangePasswordPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">TrackFlow Tech · Tu cuenta</p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Cambiar contraseña
        </h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Para cambiarla necesitas la contraseña actual. Si no la recuerdas, cierra sesión y usa «¿Olvidaste tu
          contraseña?» en la pantalla de inicio de sesión.
        </p>
      </header>

      <ChangePasswordForm />

      <p className="text-sm">
        <Link href={PROFILE_PATH} className="font-bold text-blue-700 underline-offset-2 hover:underline">
          ← Volver a Mi perfil
        </Link>
      </p>
    </div>
  );
}
