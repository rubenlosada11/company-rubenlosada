import { AREAS } from "@/lib/data/areas";
import { BASELINE_FACTS } from "@/lib/data/baseline";
import { INITIATIVES } from "@/lib/data/initiatives";
import { countByStatus } from "@/lib/initiatives";
import { PageSection } from "./PageSection";
import { StatCard } from "./StatCard";

export function Overview() {
  const byStatus = countByStatus(INITIATIVES);

  return (
    <PageSection
      id="resumen"
      title="Resumen"
      description="Situación de partida de TrackFlow según el briefing de empresa y estado del backlog de TrackFlow Tech."
    >
      <div className="space-y-6">
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-slate-500">
            Datos de partida del briefing
          </h3>
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {BASELINE_FACTS.map((fact) => (
              <StatCard key={fact.label} label={fact.label} value={fact.value} detail={fact.detail} />
            ))}
          </dl>
          <p className="mt-3 text-xs text-slate-500">
            Cifras aproximadas recogidas en CONTEXT.es.md. No son métricas en vivo: todavía no hay conexión con
            sistemas reales.
          </p>
        </div>

        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-slate-500">
            Backlog de TrackFlow Tech
          </h3>
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Áreas de negocio" value={AREAS.length} />
            <StatCard label="Iniciativas" value={INITIATIVES.length} />
            <StatCard label="Necesidades identificadas" value={byStatus.identified} />
            <StatCard label="Con base técnica disponible" value={byStatus.foundation} />
          </dl>
        </div>
      </div>
    </PageSection>
  );
}
