"use client";

import { useEffect } from "react";
import { ErrorPanel } from "@/components/ErrorPanel";
import { captureFrontendError } from "@/lib/telemetryCapture";
import "./globals.css";

/** Último recurso: un fallo en el layout raíz. Sustituye a ese layout, así que lleva sus propios <html> y <body>. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  // Telemetría: nombre del error, sección y huella; nunca el mensaje ni la traza (pueden llevar datos).
  useEffect(() => {
    void captureFrontendError(error, "global", "render_error");
  }, [error]);

  return (
    <html lang="es" className="h-full">
      <body className="min-h-full bg-slate-100 text-slate-900 antialiased">
        <main role="alert" className="flex min-h-screen items-center justify-center px-4 py-10">
          <ErrorPanel
            title="El backoffice ha tenido un problema"
            description="No se ha podido cargar la aplicación. Puedes reintentarlo o volver al inicio."
            onRetry={reset}
          />
        </main>
      </body>
    </html>
  );
}
