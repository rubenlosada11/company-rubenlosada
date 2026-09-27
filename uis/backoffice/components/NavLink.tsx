"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

interface NavLinkProps {
  href: string;
  /** Clases comunes. Colores y fondos van en `inactiveClassName`/`activeClassName` para que no se pisen. */
  className: string;
  inactiveClassName: string;
  /** Cuando `href` es la página actual (las anclas de `/` no se marcan). */
  activeClassName: string;
  children: React.ReactNode;
}

export function NavLink({ href, className, inactiveClassName, activeClassName, children }: NavLinkProps) {
  const pathname = usePathname();
  const active = !href.includes("#") && pathname === href;
  const ref = useRef<HTMLAnchorElement>(null);

  // En el menú horizontal de móvil, el enlace activo puede quedar fuera de la vista: se desplaza hasta él.
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);

  return (
    <Link
      ref={ref}
      href={href}
      aria-current={active ? "page" : undefined}
      className={`${className} ${active ? activeClassName : inactiveClassName}`}
    >
      {children}
    </Link>
  );
}
