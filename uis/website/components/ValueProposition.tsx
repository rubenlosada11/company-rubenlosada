import { VALUE_PROPOSITION } from "@/lib/content";
import { Container } from "./Container";
import { SectionHeading } from "./SectionHeading";

export function ValueProposition() {
  return (
    <section aria-labelledby="propuesta-title" className="py-14 md:py-20">
      <Container className="grid gap-8 lg:grid-cols-[1fr_1fr] lg:items-start">
        <SectionHeading
          id="propuesta-title"
          eyebrow={VALUE_PROPOSITION.eyebrow}
          title={VALUE_PROPOSITION.title}
        />
        <div className="space-y-4 text-slate-600 md:text-lg">
          {VALUE_PROPOSITION.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </Container>
    </section>
  );
}
