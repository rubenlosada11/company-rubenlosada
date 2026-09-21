import { SERVICES } from "@/lib/content";
import { Container } from "./Container";
import { Icon } from "./Icon";
import { SectionHeading } from "./SectionHeading";

export function Services() {
  return (
    <section id="servicios" aria-labelledby="servicios-title" className="scroll-mt-24 py-14 md:py-20">
      <Container>
        <SectionHeading
          id="servicios-title"
          eyebrow="Servicios"
          title="Soluciones logísticas para escalar tu operación e-commerce"
        />
        <div className="mt-10 grid gap-4 lg:grid-cols-3">
          {SERVICES.map((service) => (
            <article
              key={service.id}
              className="rounded-2xl border border-slate-200 bg-white/80 p-6 shadow-lg shadow-slate-900/5"
            >
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                <Icon name={service.icon} />
              </span>
              <h3 className="mt-4 font-heading text-xl text-slate-900">{service.title}</h3>
              <ul className="mt-4 space-y-2.5 text-slate-600">
                {service.points.map((point) => (
                  <li key={point} className="flex gap-2.5">
                    <Icon name="check" className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
