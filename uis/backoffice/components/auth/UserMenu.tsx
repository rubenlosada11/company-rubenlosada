"use client";

import { displayName, initials, ROLE_LABELS } from "@/lib/auth";
import { useAuth } from "./AuthProvider";
import { LogoutIcon } from "./LogoutIcon";

/**
 * Usuario conectado y botón de cerrar sesión en la barra superior, solo en móvil y tablet (`lg:hidden`): en
 * escritorio están al pie del sidebar (`SidebarAccount`).
 */
export function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="flex items-center gap-2 sm:gap-3 lg:hidden">
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="grid size-9 place-items-center rounded-full bg-blue-700 text-sm font-bold text-white ring-2 ring-blue-100"
        >
          {initials(user)}
        </span>
        <span className="hidden min-w-0 leading-tight sm:block">
          <span className="block max-w-[14rem] truncate text-sm font-bold text-slate-900" title={user.email}>
            {displayName(user)}
          </span>
          <span className="block text-xs font-semibold text-slate-500">{ROLE_LABELS[user.role]}</span>
        </span>
        <span className="sr-only sm:hidden">
          Sesión iniciada como {displayName(user)} ({ROLE_LABELS[user.role]})
        </span>
      </div>
      <button
        type="button"
        onClick={() => logout("logout")}
        aria-label="Cerrar sesión"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm font-bold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
      >
        <LogoutIcon />
        {/* Texto corto en móvil para que no se confunda con un icono decorativo. */}
        <span className="sm:hidden">Salir</span>
        <span className="hidden sm:inline">Cerrar sesión</span>
      </button>
    </div>
  );
}
