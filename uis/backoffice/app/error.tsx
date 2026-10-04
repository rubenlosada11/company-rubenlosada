"use client";

import { ErrorPanel } from "@/components/ErrorPanel";

/**
 * Límite de error de las pantallas sin panel (login, registro, recuperación de contraseña). El detalle técnico del
 * error no se muestra: queda en la consola del navegador.
 */
export default function RootError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
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
