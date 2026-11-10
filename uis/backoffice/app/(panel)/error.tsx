"use client";

import { useEffect } from "react";
import { ErrorPanel } from "@/components/ErrorPanel";
import { captureFrontendError } from "@/lib/telemetryCapture";

/**
 * Límite de error de las páginas del panel: el fallo se queda en el contenido y el menú lateral sigue disponible para
 * ir a otra sección. El detalle técnico del error no se muestra: queda en la consola del navegador.
 */
export default function PanelError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  // Telemetría: nombre del error, sección y huella; nunca el mensaje ni la traza (pueden llevar datos).
  useEffect(() => {
    void captureFrontendError(error, "panel", "render_error");
  }, [error]);

  return (
    <div role="alert" className="py-10">
      <ErrorPanel
        title="Algo ha fallado en esta sección"
        description="No se ha podido mostrar el contenido. Puedes reintentarlo, ir a otra sección desde el menú o volver al inicio."
        onRetry={reset}
      />
    </div>
  );
}
