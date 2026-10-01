"use client";

import { displayName, initials, PROFILE_PATH, ROLE_LABELS } from "@/lib/auth";
import { NavLink } from "../NavLink";
import { useAuth } from "./AuthProvider";
import { LogoutIcon } from "./LogoutIcon";

/** Cuenta del usuario y botón de cerrar sesión al pie del sidebar (escritorio). En móvil está en la barra superior. */
export function SidebarAccount() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <section aria-label="Tu cuenta" className="rounded-xl border border-white/10 bg-blue-900/60 p-3">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-blue-600 text-sm font-bold text-white ring-2 ring-blue-400/40"
        >
          {initials(user)}
        </span>
        <div className="min-w-0 leading-tight">
          <p className="truncate text-sm font-bold text-white">{displayName(user)}</p>
          <p className="truncate text-xs text-blue-200" title={user.email}>
            {user.email}
          </p>
          <p className="mt-0.5 text-xs font-semibold text-blue-300">{ROLE_LABELS[user.role]}</p>
        </div>
      </div>
      <NavLink
        href={PROFILE_PATH}
        className="mt-3 flex w-full items-center justify-center rounded-full px-3 py-2 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        inactiveClassName="bg-white/10 text-white hover:bg-white/20"
        activeClassName="bg-white text-blue-950"
      >
        Mi perfil
      </NavLink>
      <button
        type="button"
        onClick={() => logout("logout")}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-full border border-white/20 px-3 py-2 text-sm font-bold text-white transition hover:border-white/40 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        <LogoutIcon />
        Cerrar sesión
      </button>
    </section>
  );
}
