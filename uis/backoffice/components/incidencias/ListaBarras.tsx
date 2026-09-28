import { entero, porcentaje } from "@/lib/formato";
import type { Conteo } from "@/types/incidencias";

interface ListaBarrasProps {
  titulo: string;
  datos: Conteo;
  /** Total sobre el que se calcula el porcentaje. */
  total: number;
  etiqueta?: (clave: string) => string;
}

// Barras horizontales de una sola serie: longitud relativa al valor máximo,
// porcentaje sobre el total. El valor va escrito junto a cada barra.
export function ListaBarras({ titulo, datos, total, etiqueta = (clave) => clave }: ListaBarrasProps) {
  const entradas = Object.entries(datos);
  const maximo = Math.max(1, ...entradas.map(([, n]) => n));

  return (
    <figure className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <figcaption className="mb-4 text-sm font-bold text-slate-700">{titulo}</figcaption>
      <ul className="space-y-2.5">
        {entradas.map(([clave, n]) => (
          <li
            key={clave}
            className="grid grid-cols-[minmax(7rem,11rem)_minmax(0,1fr)] items-center gap-3 text-sm"
            title={`${etiqueta(clave)}: ${entero(n)} (${porcentaje(n, total)})`}
          >
            <span className="break-words font-medium text-slate-700">{etiqueta(clave)}</span>
            <span className="flex items-center gap-2 border-l border-slate-300">
              <span
                aria-hidden="true"
                className="h-3 rounded-r bg-blue-700"
                style={{ width: `${(n / maximo) * 75}%`, minWidth: n ? "2px" : 0 }}
              />
              <span className="shrink-0 tabular-nums text-slate-900">
                <span className="font-bold">{entero(n)}</span>
                <span className="text-slate-500"> · {porcentaje(n, total)}</span>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
