import { entero } from "@/lib/formato";
import type { Conteo } from "@/types/incidencias";

interface TablaCruceProps {
  titulo: string;
  tituloFila: string;
  datos: Record<string, Conteo>;
}

export function TablaCruce({ titulo, tituloFila, datos }: TablaCruceProps) {
  const filas = Object.entries(datos);
  const columnas = Object.keys(filas[0]?.[1] ?? {});
  const totalColumna = (columna: string) => filas.reduce((suma, [, conteo]) => suma + conteo[columna], 0);
  const totalFila = (conteo: Conteo) => Object.values(conteo).reduce((a, b) => a + b, 0);

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm">
        <caption className="px-5 pt-5 pb-3 text-left text-sm font-bold text-slate-700">{titulo}</caption>
        <thead>
          <tr className="border-y border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <th scope="col" className="px-5 py-2.5 text-left font-bold">{tituloFila}</th>
            {columnas.map((columna) => (
              <th key={columna} scope="col" className="px-3 py-2.5 text-right font-bold">{columna}</th>
            ))}
            <th scope="col" className="px-5 py-2.5 text-right font-bold">Total</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {filas.map(([fila, conteo]) => (
            <tr key={fila} className="border-b border-slate-100">
              <th scope="row" className="px-5 py-2 text-left font-semibold text-slate-800">{fila}</th>
              {columnas.map((columna) => (
                <td key={columna} className={`px-3 py-2 text-right ${conteo[columna] ? "text-slate-900" : "text-slate-400"}`}>
                  {entero(conteo[columna])}
                </td>
              ))}
              <td className="px-5 py-2 text-right font-bold text-slate-900">{entero(totalFila(conteo))}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="tabular-nums">
          <tr className="bg-slate-50">
            <th scope="row" className="px-5 py-2.5 text-left font-bold text-slate-800">Total</th>
            {columnas.map((columna) => (
              <td key={columna} className="px-3 py-2.5 text-right font-bold text-slate-900">{entero(totalColumna(columna))}</td>
            ))}
            <td className="px-5 py-2.5 text-right font-bold text-slate-900">
              {entero(filas.reduce((suma, [, conteo]) => suma + totalFila(conteo), 0))}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
