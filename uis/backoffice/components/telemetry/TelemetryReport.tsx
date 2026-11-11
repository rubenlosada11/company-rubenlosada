"use client";

import { useState } from "react";

import { ListaBarras } from "@/components/incidencias/ListaBarras";
import { LoadErrorAlert } from "@/components/LoadErrorAlert";
import { PageSection } from "@/components/PageSection";
import { StatCard } from "@/components/StatCard";
import { entero } from "@/lib/formato";
import {
  errorTypeLabel,
  longDay,
  REPORT_PERIODS,
  type ReportDays,
  reportTotals,
  shortDay,
  telemetryReportApi,
  telemetryReportErrorMessage,
  utcInstant,
} from "@/lib/telemetryReport";
import { useApiRequest } from "@/lib/useApiRequest";
import type { TelemetryReport as Report } from "@/types/telemetryReport";

const PERCENT = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
const percent = (value: number | null) => (value === null ? "—" : `${PERCENT.format(value)} %`);

/**
 * Reporte técnico de la telemetría (`GET /telemetry/report`): volumen diario, incidencias técnicas por tipo y por
 * día, tasa de fallos de inicio de sesión y envíos fallidos por formulario. Datos reales de `telemetry_events`;
 * la API los guarda 60 s en caché.
 */
export function TelemetryReport() {
  const [days, setDays] = useState<ReportDays>(7);
  const request = useApiRequest(
    String(days),
    (signal) => telemetryReportApi.get(days, signal),
    telemetryReportErrorMessage,
    { keepDataOnError: false }
  );
  const { data: report, loading, reload } = request;
  const error = !loading ? request.error : null;

  return (
    <PageSection
      id="telemetria"
      title="Telemetría técnica"
      description="Estado técnico del sistema a partir de los eventos de telemetría guardados: volumen, incidencias, inicios de sesión fallidos y envíos que la API no aceptó. Días en UTC."
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Periodo del reporte">
          {REPORT_PERIODS.map((period) => (
            <button
              key={period.days}
              type="button"
              aria-pressed={days === period.days}
              onClick={() => setDays(period.days)}
              className={`min-h-11 rounded-full border px-4 text-sm font-bold transition ${
                days === period.days
                  ? "border-blue-700 bg-blue-700 text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {period.label}
            </button>
          ))}
          <button
            type="button"
            onClick={reload}
            disabled={loading}
            className="min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
          >
            Actualizar
          </button>
          {report ? (
            <p className="text-xs text-slate-600">
              Del {utcInstant(report.period.from)} al {utcInstant(report.period.to)} (UTC)
            </p>
          ) : null}
        </div>

        {error ? (
          <LoadErrorAlert title="No se pudo cargar el reporte de telemetría." message={error} onRetry={reload} />
        ) : !report ? (
          <p
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-5 text-sm font-semibold text-slate-600 shadow-sm"
          >
            Cargando reporte de telemetría…
          </p>
        ) : (
          <div className={`space-y-5 ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <p role="status" className="sr-only">
              {loading ? "Actualizando reporte…" : "Reporte de telemetría actualizado."}
            </p>
            <ReportContent report={report} />
          </div>
        )}
      </div>
    </PageSection>
  );
}

function ReportContent({ report }: { report: Report }) {
  const totals = reportTotals(report);
  const { metrics } = report;

  if (totals.events === 0) {
    return (
      <p className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
        No hay eventos de telemetría en este periodo.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Eventos" value={entero(totals.events)} detail="Registrados en el periodo" />
        <StatCard label="Incidencias técnicas" value={entero(totals.errors)} detail="Errores del catálogo" />
        <StatCard
          label="Fallos de inicio de sesión"
          value={percent(totals.loginFailureRate)}
          detail={`${entero(totals.loginFailed)} de ${entero(totals.loginAttempts)} intentos`}
        />
        <StatCard
          label="Envíos fallidos"
          value={entero(totals.failedSubmissions)}
          detail={`De ${entero(totals.submissions)} envíos de formularios`}
        />
      </dl>

      <div className="grid gap-5 lg:grid-cols-2">
        <DailyColumns
          title="Eventos por día"
          rows={metrics.events_per_day.map((row) => ({ date: row.date, value: row.total_events }))}
          unit="eventos"
        />
        <DailyColumns
          title="Incidencias técnicas por día"
          rows={metrics.errors_per_day.map((row) => ({ date: row.date, value: row.errors }))}
          unit="incidencias"
        />
      </div>

      {metrics.error_rate_by_type.length ? (
        <ListaBarras
          titulo="Incidencias por tipo (categoría · evento · motivo)"
          datos={Object.fromEntries(metrics.error_rate_by_type.map((row) => [errorTypeLabel(row), row.errors]))}
          total={totals.errors}
        />
      ) : (
        <p className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
          Sin incidencias técnicas en este periodo.
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <DataTable
          caption="Inicios de sesión por día"
          empty="Sin intentos de inicio de sesión en este periodo."
          headers={["Día", "Fallidos", "Correctos", "Tasa de fallo"]}
          rows={metrics.auth_failure_rate.map((row) => [
            longDay(row.date),
            entero(row.failed),
            entero(row.succeeded),
            percent(row.failure_rate_pct),
          ])}
        />
        <DataTable
          caption="Envíos de formularios por formulario"
          empty="Sin envíos de formularios en este periodo."
          headers={["Formulario", "Envíos", "Fallidos", "Tasa de fallo"]}
          rows={metrics.submission_failures_by_form.map((row) => [
            row.form_id ?? "Sin formulario",
            entero(row.submissions),
            entero(row.failed),
            percent(row.failure_rate_pct),
          ])}
        />
      </div>
    </div>
  );
}

interface DailyColumnsProps {
  title: string;
  rows: { date: string; value: number }[];
  /** Unidad para el tooltip y la tabla («eventos»). */
  unit: string;
}

/** Columnas de una sola serie por día (alto relativo al máximo), con el valor en el tooltip y una tabla desplegable. */
function DailyColumns({ title, rows, unit }: DailyColumnsProps) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  // Con muchos días solo se rotulan algunos para que las etiquetas no se monten.
  const labelEvery = Math.ceil(rows.length / 8);

  return (
    <figure className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <figcaption className="mb-4 flex items-baseline justify-between gap-3 text-sm font-bold text-slate-700">
        <span>{title}</span>
        <span className="text-xs font-normal text-slate-500">Máximo: {entero(max)}</span>
      </figcaption>
      <div className="flex h-36 items-end gap-0.5 border-b border-slate-300" aria-hidden="true">
        {rows.map((row) => (
          <div
            key={row.date}
            className="group flex h-full min-w-0 flex-1 items-end"
            title={`${longDay(row.date)}: ${entero(row.value)} ${unit}`}
          >
            <div
              className="w-full rounded-t bg-blue-700 group-hover:bg-blue-900"
              style={{ height: `${(row.value / max) * 100}%`, minHeight: row.value ? "2px" : 0 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-0.5 text-[11px] text-slate-500" aria-hidden="true">
        {rows.map((row, index) => (
          <span key={row.date} className="min-w-0 flex-1 truncate text-center tabular-nums">
            {index % labelEvery === 0 ? shortDay(row.date) : ""}
          </span>
        ))}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-semibold text-blue-800">Ver tabla</summary>
        <table className="mt-2 w-full text-left">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="text-xs text-slate-500">
              <th scope="col" className="py-1 font-semibold">
                Día (UTC)
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                {unit[0].toUpperCase() + unit.slice(1)}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.date} className="border-t border-slate-100">
                <td className="py-1">{longDay(row.date)}</td>
                <td className="py-1 text-right tabular-nums">{entero(row.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

interface DataTableProps {
  caption: string;
  empty: string;
  headers: string[];
  rows: string[][];
}

function DataTable({ caption, empty, headers, rows }: DataTableProps) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <table className="w-full text-left text-sm">
        <caption className="mb-3 text-left text-sm font-bold text-slate-700">{caption}</caption>
        <thead>
          <tr className="text-xs text-slate-500">
            {headers.map((header, index) => (
              <th key={header} scope="col" className={`py-1.5 font-semibold ${index ? "text-right" : ""}`}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((cells) => (
              <tr key={cells[0]} className="border-t border-slate-100">
                {cells.map((cell, index) => (
                  <td key={index} className={`py-1.5 ${index ? "text-right tabular-nums" : "text-slate-700"}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length} className="py-2 text-slate-600">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
