import { entero } from "@/lib/formato";
import type { ResultadoAnalisis } from "@/types/incidencias";

interface RegistrosInvalidosProps {
  resultado: ResultadoAnalisis;
}

export function RegistrosInvalidos({ resultado }: RegistrosInvalidosProps) {
  const { totales, invalidos_por_regla, registros_invalidos, reglas } = resultado;
  const reglasActivadas = Object.entries(invalidos_por_regla).filter(([, n]) => n > 0);
  const hayComplementarias = reglasActivadas.some(([codigo]) => reglas[codigo]?.complementaria);
  const sumaReglas = reglasActivadas.reduce((suma, [, n]) => suma + n, 0);

  if (totales.invalidos === 0) {
    return (
      <p className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-semibold text-emerald-900">
        <span aria-hidden="true">✓</span> Todos los registros son válidos.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <p
        role="status"
        className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950"
      >
        <span aria-hidden="true" className="font-bold">⚠</span>
        <span>
          <strong>
            {entero(totales.invalidos)} {totales.invalidos === 1 ? "registro inválido o incompleto" : "registros inválidos o incompletos"}
          </strong>{" "}
          excluidos de las métricas. Se identifican por línea e ID, sin mostrar datos personales.
        </span>
      </p>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-bold text-slate-700">Por regla incumplida</h3>
          <ul className="divide-y divide-slate-100 text-sm">
            {reglasActivadas.map(([codigo, n]) => (
              <li key={codigo} className="flex justify-between gap-3 py-2">
                <span className="text-slate-700">
                  {reglas[codigo]?.etiqueta ?? codigo}
                  {reglas[codigo]?.complementaria ? " *" : ""}
                </span>
                <span className="font-bold tabular-nums text-slate-900">{entero(n)}</span>
              </li>
            ))}
          </ul>
          {hayComplementarias ? (
            <p className="mt-3 text-xs text-slate-500">* Regla complementaria: campo obligatorio según la tabla del CONTEXT.</p>
          ) : null}
          {sumaReglas > totales.invalidos ? (
            <p className="mt-3 text-xs text-slate-500">Algunos registros incumplen varias reglas y cuentan en cada una.</p>
          ) : null}
        </div>

        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <caption className="px-5 pt-5 pb-3 text-left text-sm font-bold text-slate-700">Detalle de registros</caption>
            <thead>
              <tr className="border-y border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <th scope="col" className="px-5 py-2.5 text-right font-bold">Línea</th>
                <th scope="col" className="px-3 py-2.5 text-left font-bold">ID</th>
                <th scope="col" className="px-5 py-2.5 text-left font-bold">Motivo</th>
              </tr>
            </thead>
            <tbody>
              {registros_invalidos.map((registro) => (
                <tr key={registro.linea} className="border-b border-slate-100 last:border-0">
                  <td className="px-5 py-2 text-right tabular-nums text-slate-600">{registro.linea}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-slate-900">{registro.incident_id || "(sin ID)"}</td>
                  <td className="px-5 py-2 text-slate-700">
                    {registro.reglas.map((codigo) => reglas[codigo]?.etiqueta ?? codigo).join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
