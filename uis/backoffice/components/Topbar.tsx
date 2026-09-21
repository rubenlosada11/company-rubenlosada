import Image from "next/image";
import { NAV_ITEMS } from "@/lib/nav";

export function Topbar() {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur-md">
      <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-10">
        <div className="flex items-center gap-3">
          <Image
            src="/logo/TrackFlow_Logo1_Full.png"
            alt="Logo de TrackFlow"
            width={1190}
            height={264}
            className="h-7 w-auto lg:hidden"
          />
          <span className="rounded-full bg-blue-700 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide text-white">
            Backoffice
          </span>
        </div>
        <p className="hidden text-sm font-semibold text-slate-500 sm:block">
          Panel interno · TrackFlow Tech
        </p>
      </div>

      <nav
        aria-label="Secciones del backoffice (móvil)"
        className="flex gap-2 overflow-x-auto border-t border-slate-100 px-4 py-2 sm:px-6 lg:hidden"
      >
        {NAV_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className="shrink-0 rounded-full border border-slate-300 bg-white px-3.5 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            {item.label}
          </a>
        ))}
      </nav>
    </header>
  );
}
