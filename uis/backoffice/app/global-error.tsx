"use client";

import { ErrorPanel } from "@/components/ErrorPanel";
import "./globals.css";

/** Último recurso: un fallo en el layout raíz. Sustituye a ese layout, así que lleva sus propios <html> y <body>. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
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
