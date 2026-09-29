import type { Metadata } from "next";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { safeNextPath } from "@/lib/session";

export const metadata: Metadata = {
  title: "Iniciar sesión | TrackFlow Tech",
  description: "Acceso al backoffice interno de TrackFlow Tech.",
};

interface LoginPageProps {
  searchParams: Promise<{ next?: string | string[]; motivo?: string | string[] }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next, motivo } = await searchParams;
  const reason = motivo === "caducada" || motivo === "salida" ? motivo : null;
  return <LoginScreen next={safeNextPath(typeof next === "string" ? next : null)} reason={reason} />;
}
