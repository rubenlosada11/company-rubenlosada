"use client";

import { ErrorPanel } from "@/components/ErrorPanel";

/**
 * Límite de error de las páginas del panel: el fallo se queda en el contenido y el menú lateral sigue disponible para
 * ir a otra sección. El detalle técnico del error no se muestra: queda en la consola del navegador.
 */
export default function PanelError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
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
