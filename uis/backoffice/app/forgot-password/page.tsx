import type { Metadata } from "next";
import { ForgotPasswordScreen } from "@/components/auth/ForgotPasswordScreen";

export const metadata: Metadata = {
  title: "Recuperar contraseña | TrackFlow Tech",
  description: "Pide un enlace para restablecer la contraseña de tu cuenta del backoffice de TrackFlow Tech.",
};

/** Pública: fuera de `app/(panel)/`. Se puede abrir con o sin sesión. */
export default function ForgotPasswordPage() {
  return <ForgotPasswordScreen />;
}
