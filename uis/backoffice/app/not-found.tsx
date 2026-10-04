import type { Metadata } from "next";
import { ErrorPanel } from "@/components/ErrorPanel";

export const metadata: Metadata = {
  title: "Página no encontrada | TrackFlow Tech",
};

export default function NotFound() {
  return (
    <main id="contenido" className="flex min-h-screen items-center justify-center px-4 py-10">
      <ErrorPanel
        title="Página no encontrada"
        description="La dirección no corresponde a ninguna página del backoffice. Comprueba el enlace o vuelve al inicio."
      />
    </main>
  );
}
