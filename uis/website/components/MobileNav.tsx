"use client";

import { useState } from "react";
import { NAV_ITEMS, SITE } from "@/lib/content";
import { ButtonLink } from "./ButtonLink";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="mobile-menu"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-800 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
      >
        <span className="sr-only">{open ? "Cerrar menú" : "Abrir menú"}</span>
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden="true">
          {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>

      {open ? (
        <nav
          id="mobile-menu"
          aria-label="Navegación principal (móvil)"
          className="absolute inset-x-0 top-full border-b border-slate-200 bg-white px-[4vw] pb-5 pt-2 shadow-xl"
        >
          <ul className="flex flex-col">
            {NAV_ITEMS.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="block border-b border-slate-100 py-3 text-base font-semibold text-slate-700 hover:text-slate-900"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <ButtonLink href={SITE.leadFormUrl} external className="mt-4 w-full">
            Solicitar información
          </ButtonLink>
        </nav>
      ) : null}
    </div>
  );
}
