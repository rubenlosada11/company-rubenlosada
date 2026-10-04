import type { Metadata } from "next";
import { ButtonLink } from "@/components/ButtonLink";
import { Container } from "@/components/Container";

export const metadata: Metadata = {
  title: "Página no encontrada | TrackFlow",
};

export default function NotFound() {
  return (
    <Container className="py-24 text-center sm:py-32">
      <p className="text-xs font-bold uppercase tracking-[0.17em] text-blue-800">Error 404</p>
      <h1 className="mt-3 font-heading text-3xl tracking-tight text-slate-900 sm:text-4xl">Página no encontrada</h1>
      <p className="mx-auto mt-4 max-w-xl text-slate-600">
        La dirección no corresponde a ninguna página de este sitio. Comprueba el enlace o vuelve al inicio.
      </p>
      <div className="mt-8">
        <ButtonLink href="/">Volver al inicio</ButtonLink>
      </div>
    </Container>
  );
}
