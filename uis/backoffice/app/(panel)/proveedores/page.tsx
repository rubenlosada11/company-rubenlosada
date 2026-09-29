import type { Metadata } from "next";
import { SupplierDirectory } from "@/components/SupplierDirectory";

export const metadata: Metadata = {
  title: "Directorio de proveedores | TrackFlow Tech",
  description: "Registro centralizado de proveedores de TrackFlow en USA y España.",
};

export default function SuppliersPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">
          TrackFlow Tech · Carrier Operations
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Directorio de proveedores
        </h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Registro centralizado de carriers, suministros de almacén, embalaje y software operacional de Los Ángeles
          y Zaragoza. Sustituye a las hojas de cálculo de cada mercado: los datos se leen y se guardan en la API de
          proveedores.
        </p>
      </header>

      <SupplierDirectory />
    </div>
  );
}
