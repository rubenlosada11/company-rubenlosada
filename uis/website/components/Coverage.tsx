import { COVERAGE } from "@/lib/content";
import { Container } from "./Container";
import { Icon } from "./Icon";
import { SectionHeading } from "./SectionHeading";

export function Coverage() {
  return (
    <section id="cobertura" aria-labelledby="cobertura-title" className="scroll-mt-24 py-14 md:py-20">
      <Container>
        <SectionHeading id="cobertura-title" eyebrow={COVERAGE.eyebrow} title={COVERAGE.title} />
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {COVERAGE.regions.map((region) => (
            <article
              key={region.id}
              className="rounded-2xl border border-slate-200 bg-gradient-to-b from-white to-blue-50 p-6 shadow-lg shadow-slate-900/5"
            >
              <h3 className="font-heading text-2xl text-slate-900">{region.country}</h3>
              <ul className="mt-4 space-y-2.5 text-slate-700">
                {region.points.map((point) => (
                  <li key={point} className="flex gap-2.5">
                    <Icon name="pin" className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-5 border-t border-dashed border-slate-300 pt-4">
                <p className="text-xs font-bold uppercase tracking-[0.17em] text-slate-500">Carriers</p>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {region.carriers.map((carrier) => (
                    <li
                      key={carrier}
                      className="rounded-full border border-slate-300 bg-white px-3 py-1 text-sm font-bold text-slate-700"
                    >
                      {carrier}
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
