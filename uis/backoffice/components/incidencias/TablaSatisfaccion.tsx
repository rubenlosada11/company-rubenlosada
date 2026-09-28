import { entero, media, PUNTUACION_MAXIMA } from "@/lib/formato";
import type { Satisfaccion } from "@/types/incidencias";

interface TablaSatisfaccionProps {
  titulo: string;
  tituloFila: string;
  datos: Record<string, Satisfaccion>;
}

export function TablaSatisfaccion({ titulo, tituloFila, datos }: TablaSatisfaccionProps) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm">
        <caption className="px-5 pt-5 pb-3 text-left text-sm font-bold text-slate-700">{titulo}</caption>
        <thead>
          <tr className="border-y border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <th scope="col" className="px-5 py-2.5 text-left font-bold">{tituloFila}</th>
            <th scope="col" className="px-3 py-2.5 text-right font-bold">Cerradas</th>
            <th scope="col" className="px-3 py-2.5 text-right font-bold">Con puntuación</th>
            <th scope="col" className="px-5 py-2.5 text-left font-bold">Media (1–5)</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {Object.entries(datos).map(([grupo, s]) => (
            <tr key={grupo} className="border-b border-slate-100 last:border-0">
              <th scope="row" className="px-5 py-2 text-left font-semibold text-slate-800">{grupo}</th>
              <td className="px-3 py-2 text-right text-slate-900">{entero(s.cerradas)}</td>
              <td className="px-3 py-2 text-right text-slate-900">{entero(s.con_puntuacion)}</td>
              <td className="px-5 py-2">
                <span className="flex items-center gap-2">
                  <span className="w-10 font-bold text-slate-900">{media(s.media)}</span>
                  <span aria-hidden="true" className="h-2 w-24 rounded-full bg-blue-100">
                    <span
                      className="block h-2 rounded-full bg-blue-700"
                      style={{ width: `${((s.media ?? 0) / PUNTUACION_MAXIMA) * 100}%` }}
                    />
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
