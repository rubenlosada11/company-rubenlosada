import Image from "next/image";
import { NAV_ITEMS, SITE } from "@/lib/content";
import { ButtonLink } from "./ButtonLink";
import { Container } from "./Container";
import { MobileNav } from "./MobileNav";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
      <Container className="relative flex min-h-[74px] items-center justify-between gap-4">
        <a href="#inicio" className="inline-flex items-center" aria-label="TrackFlow, ir al inicio">
          <Image
            src="/logo/TrackFlow_Logo1_Full.png"
            alt="Logo de TrackFlow"
            width={1190}
            height={264}
            priority
            className="h-8 w-auto max-w-[180px] object-contain sm:h-9 sm:max-w-[210px] md:h-10 md:max-w-[250px]"
          />
        </a>

        <nav aria-label="Navegación principal" className="hidden items-center gap-6 text-sm font-semibold text-slate-600 md:flex">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} className="transition hover:text-slate-900">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ButtonLink href={SITE.leadFormUrl} external className="hidden !py-2 sm:inline-flex">
            Solicitar información
          </ButtonLink>
          <MobileNav />
        </div>
      </Container>
    </header>
  );
}
