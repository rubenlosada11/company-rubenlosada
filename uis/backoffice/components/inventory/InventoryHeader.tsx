import { NavLink } from "@/components/NavLink";

/** Las cuatro vistas del inventario, en el orden de trabajo habitual. */
const INVENTORY_LINKS = [
  { href: "/inventory/products", label: "Productos y stock" },
  { href: "/inventory/orders/inbound", label: "Registrar entrada" },
  { href: "/inventory/orders/outbound", label: "Registrar salida" },
  { href: "/inventory/orders", label: "Historial de movimientos" },
] as const;

interface InventoryHeaderProps {
  title: string;
  description: string;
}

/** Cabecera común de las páginas del inventario, con los enlaces entre sus cuatro vistas. */
export function InventoryHeader({ title, description }: InventoryHeaderProps) {
  return (
    <header>
      <p className="mb-3 text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">
        TrackFlow Tech · Inventario Los Ángeles y Zaragoza
      </p>
      <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
      <p className="mt-3 max-w-3xl text-slate-600">{description}</p>

      <nav aria-label="Vistas del inventario" className="mt-5 flex flex-wrap gap-2">
        {INVENTORY_LINKS.map((link) => (
          <NavLink
            key={link.href}
            href={link.href}
            className="inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            inactiveClassName="border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            activeClassName="border-blue-700 bg-blue-700 text-white hover:bg-blue-800"
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
