import { PROCESS } from "@/lib/content";
import { Container } from "./Container";
import { SectionHeading } from "./SectionHeading";

export function Process() {
  return (
    <section aria-labelledby="proceso-title" className="py-14 md:py-20">
      <Container>
        <SectionHeading id="proceso-title" eyebrow={PROCESS.eyebrow} title={PROCESS.title} />
        <ol className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {PROCESS.steps.map((step, index) => (
            <li
              key={step.title}
              className="relative rounded-2xl border border-slate-200 bg-white/80 p-6 shadow-lg shadow-slate-900/5"
            >
              <span
                className="font-heading text-4xl text-blue-200"
                aria-hidden="true"
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-2 font-heading text-lg text-slate-900">
                <span className="sr-only">Paso {index + 1}: </span>
                {step.title}
              </h3>
              <p className="mt-2 text-slate-600">{step.description}</p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
