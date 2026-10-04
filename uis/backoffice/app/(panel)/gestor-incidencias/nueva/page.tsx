import type { Metadata } from "next";
import Link from "next/link";
import { IncidentForm } from "@/components/gestor-incidencias/IncidentForm";

export const metadata: Metadata = {
  title: "Registrar incidencia | TrackFlow Tech",
  description: "Registro de incidencias operativas y de clientes de TrackFlow.",
};

export default function NewIncidentPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">
          TrackFlow Tech · Gestor de incidencias
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Registrar incidencia
        </h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Paquetes extraviados, fallos de carrier, discrepancias de inventario, devoluciones o quejas de clientes:
          cada incidencia queda registrada, categorizada y asociada a una sede.
        </p>
        <Link
          href="/gestor-incidencias"
          className="mt-4 inline-flex min-h-11 items-center rounded-full border border-slate-300 bg-white px-5 text-sm font-bold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          Ver incidencias
        </Link>
      </header>

      <IncidentForm />
    </div>
  );
}
