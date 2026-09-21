import { AUDIENCE } from "@/lib/content";
import { Container } from "./Container";
import { SectionHeading } from "./SectionHeading";

export function Audience() {
  return (
    <section aria-labelledby="audiencia-title" className="py-14 md:py-20">
      <Container>
        <div className="grid gap-8 rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-lg shadow-slate-900/5 sm:p-10 lg:grid-cols-[1.1fr_0.9fr]">
          <SectionHeading
            id="audiencia-title"
            eyebrow={AUDIENCE.eyebrow}
            title={AUDIENCE.title}
            description={AUDIENCE.description}
          />
          <div className="space-y-6">
            <ul className="flex flex-wrap gap-3" aria-label="Sectores con los que trabajamos">
              {AUDIENCE.segments.map((segment) => (
                <li
                  key={segment}
                  className="rounded-full bg-blue-700 px-5 py-2 text-sm font-bold text-white"
                >
                  {segment}
                </li>
              ))}
            </ul>
            <ul className="space-y-3 border-l-2 border-blue-200 pl-4 text-sm text-slate-600">
              {AUDIENCE.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        </div>
      </Container>
    </section>
  );
}
