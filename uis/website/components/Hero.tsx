import Image from "next/image";
import { FACTS, HERO, SITE } from "@/lib/content";
import { ButtonLink } from "./ButtonLink";
import { Container } from "./Container";

export function Hero() {
  return (
    <section id="inicio" aria-labelledby="hero-title" className="scroll-mt-24 py-14 md:py-20">
      <Container className="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">{HERO.eyebrow}</p>
          <h1
            id="hero-title"
            className="max-w-[19ch] font-heading text-4xl leading-[1.03] tracking-tight text-slate-900 sm:text-5xl md:text-6xl"
          >
            {HERO.title}
          </h1>
          <p className="mt-5 max-w-2xl text-slate-600 md:text-lg">{HERO.subtitle}</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <ButtonLink href={SITE.leadFormUrl} external>
              {HERO.primaryCta}
            </ButtonLink>
            <ButtonLink href="#servicios" variant="secondary">
              {HERO.secondaryCta}
            </ButtonLink>
          </div>
        </div>

        <figure className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/10">
          <Image
            src="/images/logistics-trackflow.jpg"
            alt={HERO.imageAlt}
            width={1024}
            height={559}
            priority
            sizes="(min-width: 1024px) 480px, 92vw"
            className="h-auto w-full"
          />
        </figure>
      </Container>

      <Container className="mt-12">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 shadow-lg shadow-slate-900/5 lg:grid-cols-5">
          {FACTS.map((fact, index) => (
            <div
              key={fact.label}
              className={`flex flex-col-reverse justify-end bg-white/90 p-5 ${
                // Con un número impar de datos, el último ocupa el ancho completo en la rejilla de 2 columnas.
                FACTS.length % 2 === 1 && index === FACTS.length - 1 ? "col-span-2 lg:col-span-1" : ""
              }`}
            >
              <dt className="mt-1 text-sm text-slate-600">{fact.label}</dt>
              <dd className="font-heading text-3xl text-blue-800">{fact.value}</dd>
            </div>
          ))}
        </dl>
      </Container>
    </section>
  );
}
