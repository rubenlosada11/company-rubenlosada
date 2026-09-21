import { BENEFITS } from "@/lib/content";
import { Container } from "./Container";
import { Icon } from "./Icon";
import { SectionHeading } from "./SectionHeading";

export function WhyTrackFlow() {
  return (
    <section aria-labelledby="beneficios-title" className="py-14 md:py-20">
      <Container>
        <SectionHeading id="beneficios-title" eyebrow={BENEFITS.eyebrow} title={BENEFITS.title} />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {BENEFITS.items.map((benefit) => (
            <li
              key={benefit.title}
              className="rounded-2xl border border-slate-200 bg-white/80 p-6 shadow-lg shadow-slate-900/5"
            >
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-blue-700 text-white">
                <Icon name={benefit.icon} className="h-5 w-5" />
              </span>
              <h3 className="mt-4 font-heading text-lg text-slate-900">{benefit.title}</h3>
              <p className="mt-2 text-slate-600">{benefit.description}</p>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
