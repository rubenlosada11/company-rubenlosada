import type { Metadata } from "next";
import { IncidentDashboard } from "@/components/gestor-incidencias/IncidentDashboard";

export const metadata: Metadata = {
  title: "Incidencias | TrackFlow Tech",
  description: "Gestor centralizado de incidencias de TrackFlow en Los Ángeles y Zaragoza.",
};

export default function IncidentsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">
          TrackFlow Tech · Gestor de incidencias
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">Incidencias</h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Registro centralizado de las incidencias de clientes, sedes y equipos internos de Los Ángeles y Zaragoza.
          Cada una queda categorizada, asociada a una sede y con su estado al día.
        </p>
      </header>

      <IncidentDashboard />
    </div>
  );
}
