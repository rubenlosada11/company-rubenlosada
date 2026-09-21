import { MILESTONES } from "@/lib/data/milestones";
import { Badge } from "./Badge";
import { PageSection } from "./PageSection";

export function Milestones() {
  return (
    <PageSection
      id="hitos"
      title="Hitos del proyecto"
      description="Entregables del proyecto transversal, con su ubicación en el monorepo."
    >
      <ol className="space-y-3">
        {MILESTONES.map((milestone) => (
          <li key={milestone.number} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="font-heading text-lg text-slate-900">
                Hito {milestone.number} — {milestone.name}
              </h3>
              <Badge tone={milestone.status === "delivered" ? "emerald" : "blue"}>
                {milestone.status === "delivered" ? "Entregado" : "En curso"}
              </Badge>
            </div>
            <p className="mt-2 text-sm text-slate-600">{milestone.summary}</p>
            <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>
                Ubicación: <span className="font-mono text-slate-700">{milestone.paths.join(" · ")}</span>
              </span>
              {milestone.demoUrl ? (
                <a
                  href={milestone.demoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-blue-700 underline-offset-2 hover:underline"
                >
                  Demo pública
                </a>
              ) : null}
            </p>
          </li>
        ))}
      </ol>
    </PageSection>
  );
}
