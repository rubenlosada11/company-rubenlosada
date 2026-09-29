"use client";

import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "./AuthProvider";

/**
 * Muestra el panel solo con una sesión válida; si no, lleva a `/login?next=<ruta actual>`.
 *
 * Es una comprobación de interfaz: lo que protege los datos es la API, que exige el token en cada petición.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status, endReason, connectionError, retry, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status !== "anonymous") return;
    const params = new URLSearchParams({ next: pathname });
    if (endReason === "expired") params.set("motivo", "caducada");
    if (endReason === "logout") params.set("motivo", "salida");
    router.replace(`/login?${params}`);
  }, [status, endReason, pathname, router]);

  if (status === "authenticated") return <>{children}</>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="flex w-full max-w-sm flex-col items-center text-center">
        <Image
          src="/logo/TrackFlow_Logo1_Full.png"
          alt="Logo de TrackFlow"
          width={1190}
          height={264}
          priority
          className="h-8 w-auto"
        />

        {status === "unreachable" ? (
          <div role="alert" className="mt-8 w-full rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
            <h1 className="font-heading text-lg text-slate-900">No se pudo comprobar tu sesión</h1>
            <p className="mt-2 text-sm text-slate-600">{connectionError}</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={retry}
                className="rounded-full bg-blue-700 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
              >
                Reintentar
              </button>
              <button
                type="button"
                onClick={() => logout("logout")}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
              >
                Ir al inicio de sesión
              </button>
            </div>
          </div>
        ) : (
          <p role="status" className="mt-8 flex items-center gap-3 text-sm font-semibold text-slate-500">
            <Spinner className="size-5 text-blue-700" />
            Comprobando tu sesión…
          </p>
        )}
      </div>
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={`animate-spin ${className}`}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
