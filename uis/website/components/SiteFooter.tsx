import { NAV_ITEMS, SITE } from "@/lib/content";
import { Container } from "./Container";
import { Icon } from "./Icon";

export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-blue-900/60 bg-blue-950 py-8 text-blue-100">
      <Container className="flex flex-col gap-6 text-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-heading text-lg text-white">TrackFlow</p>
          <p className="mt-1 text-blue-200">Los Ángeles (EE. UU.) · Zaragoza (España)</p>
          <p className="mt-3 text-blue-200">
            © {year} {SITE.name}. Todos los derechos reservados.
          </p>
        </div>
        <nav aria-label="Enlaces de pie de página" className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} className="transition hover:text-white">
              {item.label}
            </a>
          ))}
          <a
            href={SITE.linkedinUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 font-semibold text-white transition hover:text-blue-200"
          >
            <Icon name="linkedin" className="h-5 w-5" />
            LinkedIn
          </a>
        </nav>
      </Container>
    </footer>
  );
}
