import type { Metadata } from "next";

import { WeeklyPerformanceDashboard } from "@/components/reporting/WeeklyPerformanceDashboard";

export const metadata: Metadata = {
  title: "Desempeño semanal | TrackFlow Tech",
  description: "Reporte Semanal de Desempeño por Almacén y Cliente: volumen de entrada, throughput de salida, quiebres de stock y tasa de discrepancia.",
};

export default function ReportingPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">
          TrackFlow Tech · Reporte para dirección
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Desempeño semanal por almacén y cliente
        </h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          El Reporte Semanal de Desempeño por Almacén y Cliente: cuánto recibió y despachó cada almacén para cada
          cliente, cuántas veces se quedó un producto por debajo de su mínimo y qué parte de los pedidos tuvo
          discrepancias de inventario. Se calcula por semanas completas a partir de la operación registrada.
        </p>
      </header>
      <WeeklyPerformanceDashboard />
    </div>
  );
}
