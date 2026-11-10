"use client";

import { useEffect } from "react";
import { ErrorPanel } from "@/components/ErrorPanel";
import { captureFrontendError } from "@/lib/telemetryCapture";

/**
 * Límite de error de las pantallas sin panel (login, registro, recuperación de contraseña). El detalle técnico del
 * error no se muestra: queda en la consola del navegador.
 */
export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  // Telemetría: nombre del error, sección y huella; nunca el mensaje ni la traza (pueden llevar datos).
  useEffect(() => {
    void captureFrontendError(error, "root", "render_error");
  }, [error]);

  return (
    <main id="contenido" role="alert" className="flex min-h-screen items-center justify-center px-4 py-10">
      <ErrorPanel
        title="Algo ha fallado en esta pantalla"
        description="No se ha podido mostrar la página. Puedes reintentarlo o volver al inicio."
        onRetry={reset}
      />
    </main>
  );
}
