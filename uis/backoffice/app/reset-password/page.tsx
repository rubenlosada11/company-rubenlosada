import type { Metadata } from "next";
import { ResetPasswordScreen } from "@/components/auth/ResetPasswordScreen";

export const metadata: Metadata = {
  title: "Restablecer contraseña | TrackFlow Tech",
  description: "Elige una contraseña nueva para tu cuenta del backoffice de TrackFlow Tech.",
  // La URL lleva el token del email: que no salga en la cabecera Referer hacia ningún otro sitio.
  referrer: "no-referrer",
};

interface ResetPasswordPageProps {
  searchParams: Promise<{ token?: string | string[] }>;
}

// Dinámica, como /login: el token se lee en el servidor y el formulario sale en el HTML sin esperar a la hidratación.
export default async function ResetPasswordPage({ searchParams }: ResetPasswordPageProps) {
  const { token } = await searchParams;
  const value = typeof token === "string" ? token.trim() : "";
  return <ResetPasswordScreen token={value || null} />;
}
