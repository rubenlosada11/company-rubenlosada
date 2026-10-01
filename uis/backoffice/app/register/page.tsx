import type { Metadata } from "next";
import { RegisterScreen } from "@/components/auth/RegisterScreen";
import { safeNextPath } from "@/lib/session";

export const metadata: Metadata = {
  title: "Crear cuenta | TrackFlow Tech",
  description: "Alta en el backoffice interno de TrackFlow Tech.",
};

interface RegisterPageProps {
  searchParams: Promise<{ next?: string | string[] }>;
}

// Dinámica, como /login: `next` se lee en el servidor y el formulario sale en el HTML sin esperar a la hidratación.
export default async function RegisterPage({ searchParams }: RegisterPageProps) {
  const { next } = await searchParams;
  return <RegisterScreen next={safeNextPath(typeof next === "string" ? next : null)} />;
}
