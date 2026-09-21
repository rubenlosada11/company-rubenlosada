import { CONTACT, SITE } from "@/lib/content";
import { ButtonLink } from "./ButtonLink";
import { Container } from "./Container";
import { Icon } from "./Icon";

export function Contact() {
  return (
    <section id="contacto" aria-labelledby="contacto-title" className="scroll-mt-24 py-14 md:py-20">
      <Container>
        <div className="grid gap-8 rounded-3xl bg-blue-950 p-6 text-blue-100 shadow-2xl shadow-blue-950/30 sm:p-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="mb-4 text-xs font-bold uppercase tracking-[0.17em] text-blue-300">{CONTACT.eyebrow}</p>
            <h2 id="contacto-title" className="max-w-[24ch] font-heading text-3xl leading-tight text-white sm:text-4xl">
              {CONTACT.title}
            </h2>
            <p className="mt-4 max-w-xl text-blue-100/90 md:text-lg">{CONTACT.description}</p>
            <ButtonLink href={SITE.leadFormUrl} external variant="inverse" className="mt-7">
              Solicitar información
            </ButtonLink>
          </div>

          <div className="space-y-4">
            <a
              href={`mailto:${SITE.email}`}
              className="flex items-center gap-3 rounded-2xl border border-blue-800 bg-blue-900/40 p-4 transition hover:bg-blue-900/70"
            >
              <Icon name="mail" className="h-6 w-6 shrink-0 text-blue-300" />
              <span>
                <span className="block text-xs font-bold uppercase tracking-[0.17em] text-blue-300">Email</span>
                <span className="font-semibold text-white">{SITE.email}</span>
              </span>
            </a>
            {CONTACT.offices.map((office) => (
              <a
                key={office.id}
                href={office.phoneHref}
                className="flex items-center gap-3 rounded-2xl border border-blue-800 bg-blue-900/40 p-4 transition hover:bg-blue-900/70"
              >
                <Icon name="phone" className="h-6 w-6 shrink-0 text-blue-300" />
                <span>
                  <span className="block text-xs font-bold uppercase tracking-[0.17em] text-blue-300">
                    {office.city} · {office.country}
                  </span>
                  <span className="font-semibold text-white">{office.phone}</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      </Container>
    </section>
  );
}
