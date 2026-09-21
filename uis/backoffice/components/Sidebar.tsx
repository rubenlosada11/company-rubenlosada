import Image from "next/image";
import { NAV_ITEMS } from "@/lib/nav";

export function Sidebar() {
  return (
    <aside className="hidden bg-blue-950 text-blue-100 lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:gap-8 lg:p-5">
      <div className="rounded-xl bg-white p-3">
        <Image
          src="/logo/TrackFlow_Logo1_Full.png"
          alt="Logo de TrackFlow"
          width={1190}
          height={264}
          priority
          className="h-auto w-full"
        />
      </div>

      <nav aria-label="Secciones del backoffice">
        <p className="mb-3 px-3 text-xs font-bold uppercase tracking-[0.17em] text-blue-300">Backoffice</p>
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                className="block rounded-lg px-3 py-2.5 text-sm font-semibold text-blue-100 transition hover:bg-blue-900 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <p className="mt-auto px-3 text-xs leading-relaxed text-blue-300">
        TrackFlow Tech · Uso interno. Los datos proceden de CONTEXT.es.md; no hay conexión con sistemas reales.
      </p>
    </aside>
  );
}
