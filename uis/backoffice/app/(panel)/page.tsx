import { Explorer } from "@/components/Explorer";
import { Milestones } from "@/components/Milestones";
import { Overview } from "@/components/Overview";
import { TelemetryReport } from "@/components/telemetry/TelemetryReport";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl space-y-12">
      <header>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">
          TrackFlow Tech · Uso interno
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Backoffice de TrackFlow
        </h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Estructura del negocio, backlog de iniciativas de TrackFlow Tech, estado de los hitos del proyecto, a
          partir del contexto de empresa, y estado técnico del sistema a partir de la telemetría.
        </p>
      </header>

      <Overview />
      <Explorer />
      <Milestones />
      <TelemetryReport />
    </div>
  );
}
