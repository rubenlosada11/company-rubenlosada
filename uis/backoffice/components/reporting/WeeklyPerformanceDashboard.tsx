"use client";

import { useState } from "react";

import { LoadErrorAlert } from "@/components/LoadErrorAlert";
import { PageSection } from "@/components/PageSection";
import { StatCard } from "@/components/StatCard";
import { entero } from "@/lib/formato";
import { useApiRequest } from "@/lib/useApiRequest";
import {
  addDays,
  formatDiscrepancies,
  formatKpi,
  formatOrders,
  formatRate,
  groupByWarehouse,
  HISTORY_WEEKS,
  historyRows,
  type KpiKey,
  KPIS,
  lastCompleteWeek,
  shortWeekLabel,
  unmeasuredNotices,
  utcDateTime,
  warehouseName,
  weekPeriodLabel,
  weeklyPerformanceApi,
  weeklyPerformanceErrorMessage,
  weeksBehind,
} from "@/lib/weeklyPerformance";
import type { PipelineRunSummary, WeeklyPerformanceEntry, WeeklyPerformanceReport } from "@/types/weeklyPerformance";

const BUTTON =
  "min-h-11 rounded-full border px-4 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50";
const BUTTON_IDLE = "border-slate-300 bg-white text-slate-700 hover:bg-slate-50";
const BUTTON_ACTIVE = "border-blue-700 bg-blue-700 text-white";
const PANEL = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

/**
 * Dashboard del Reporte Semanal de Desempeño por Almacén y Cliente para dirección (Thomas, CEO, y Ana, Head of
 * Warehouse Operations). Muestra lo que devuelve `GET /reporting/weekly-warehouse-client-performance`: los cuatro KPIs
 * de cada almacén y cliente en una semana ISO, la semana anterior/siguiente y la evolución de las últimas semanas.
 * No calcula ningún KPI: solo los presenta.
 */
export function WeeklyPerformanceDashboard() {
  // `null` = la semana calculada más reciente (la que elige la API).
  const [week, setWeek] = useState<string | null>(null);
  const [latestWeek, setLatestWeek] = useState<string | null>(null);

  const request = useApiRequest(
    week ?? "latest",
    (signal) => weeklyPerformanceApi.get(week, signal),
    weeklyPerformanceErrorMessage,
    {
      onSuccess: (report) => {
        if (week === null) setLatestWeek(report?.week_start ?? null);
      },
    }
  );
  const lastRun = useApiRequest("latest-run", (signal) => weeklyPerformanceApi.latestRun(signal), () => "");

  const { data: report, loading, settled, reload } = request;
  const error = !loading ? request.error : null;
  const shownWeek = report?.week_start ?? week;

  return (
    <div className="space-y-8">
      <div className={`${PANEL} space-y-4`}>
        <WeekNavigation
          shownWeek={shownWeek}
          latestWeek={latestWeek}
          loading={loading}
          onChange={setWeek}
          onLatest={() => setWeek(null)}
        />
        <RunStatus run={lastRun.data} />
        {latestWeek ? <Freshness latestWeek={latestWeek} /> : null}
      </div>

      {error ? (
        <LoadErrorAlert title="No se pudo cargar el reporte semanal." message={error} onRetry={reload} />
      ) : !settled ? (
        <p role="status" className={`${PANEL} text-sm font-semibold text-slate-600`}>
          Cargando el reporte semanal…
        </p>
      ) : report === null ? (
        <NotComputed week={week} onLatest={() => setWeek(null)} />
      ) : report ? (
        <div className={`space-y-10 ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <p role="status" className="sr-only">
            {loading ? "Actualizando el reporte…" : `Reporte de la ${weekPeriodLabel(report.week_start)}.`}
          </p>
          <WeekReport report={report} />
          <History lastWeek={report.week_start} />
        </div>
      ) : null}

      <KpiDefinitions />
    </div>
  );
}

// --- Período y estado del cálculo ------------------------------------------------------------------------------------

interface WeekNavigationProps {
  shownWeek: string | null;
  latestWeek: string | null;
  loading: boolean;
  onChange: (week: string) => void;
  onLatest: () => void;
}

function WeekNavigation({ shownWeek, latestWeek, loading, onChange, onLatest }: WeekNavigationProps) {
  const atLatest = !shownWeek || !latestWeek || shownWeek >= latestWeek;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-xs font-bold tracking-[0.12em] text-slate-500 uppercase">Período del reporte</p>
        <p className="mt-1 text-lg font-bold text-slate-900">
          {shownWeek ? weekPeriodLabel(shownWeek) : "Semana más reciente calculada"}
        </p>
        <p className="text-xs text-slate-500">Semana ISO de lunes 00:00 a domingo 23:59 (hora UTC).</p>
      </div>
      <nav aria-label="Cambiar de semana" className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`${BUTTON} ${BUTTON_IDLE}`}
          disabled={!shownWeek || loading}
          onClick={() => shownWeek && onChange(addDays(shownWeek, -7))}
        >
          ← Semana anterior
        </button>
        <button
          type="button"
          className={`${BUTTON} ${BUTTON_IDLE}`}
          disabled={atLatest || loading}
          onClick={() => shownWeek && onChange(addDays(shownWeek, 7))}
        >
          Semana siguiente →
        </button>
        <button type="button" className={`${BUTTON} ${BUTTON_IDLE}`} disabled={atLatest || loading} onClick={onLatest}>
          Más reciente
        </button>
      </nav>
    </div>
  );
}

/** Última ejecución del cálculo: cuándo se actualizó y si la última vez falló (los datos son del último correcto). */
function RunStatus({ run }: { run: PipelineRunSummary | null }) {
  if (!run) return null;
  if (run.outcome === "running") {
    return <p className="text-sm text-slate-600">Hay un cálculo del reporte en curso; los datos se actualizarán al terminar.</p>;
  }
  if (run.outcome === "failed") {
    return (
      <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <span aria-hidden="true">⚠ </span>
        El último intento de cálculo ({utcDateTime(run.started_at)} UTC) no se completó. Se muestran los datos del último
        cálculo correcto.
      </p>
    );
  }
  return (
    <p className="text-sm text-slate-600">
      Último cálculo del reporte: {run.finished_at ? `${utcDateTime(run.finished_at)} UTC` : "—"} (semanas del{" "}
      {weekShort(run.week_from)} al {weekShort(run.week_to)}).
    </p>
  );
}

/**
 * Frescura del dato (Fase 7 del Hito 6): si hay semanas completas posteriores a la más reciente calculada, el reporte
 * no está al día y la persona que lo lee debe saberlo antes de tomar decisiones con él.
 */
function Freshness({ latestWeek }: { latestWeek: string }) {
  const behind = weeksBehind(latestWeek);
  if (behind === 0) return null;
  const missing = lastCompleteWeek();
  return (
    <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900" role="note">
      <span aria-hidden="true">⚠ </span>
      El reporte no está al día: la semana más reciente calculada es la {shortWeekLabel(latestWeek)}, y{" "}
      {behind === 1
        ? `la ${shortWeekLabel(missing)} ya terminó pero aún no se ha calculado.`
        : `hay ${behind} semanas completas posteriores sin calcular (hasta la ${shortWeekLabel(missing)}).`}
    </p>
  );
}

function weekShort(weekStart: string): string {
  return shortWeekLabel(weekStart).split(" · ")[1];
}

function NotComputed({ week, onLatest }: { week: string | null; onLatest: () => void }) {
  return (
    <div role="status" className={`${PANEL} text-sm text-slate-700`}>
      {week === null ? (
        <>
          <p className="font-bold">Todavía no hay ninguna semana calculada.</p>
          <p className="mt-1">
            El reporte se calcula por semanas completas, de lunes a domingo. Cuando se calcule la primera, aparecerá aquí.
          </p>
        </>
      ) : (
        <>
          <p className="font-bold">La {weekPeriodLabel(week)} no está calculada.</p>
          <p className="mt-1">No hay datos del reporte para esa semana.</p>
          <button type="button" onClick={onLatest} className={`${BUTTON} ${BUTTON_IDLE} mt-3`}>
            Ir a la semana más reciente
          </button>
        </>
      )}
    </div>
  );
}

// --- Semana ----------------------------------------------------------------------------------------------------------

function WeekReport({ report }: { report: WeeklyPerformanceReport }) {
  const groups = groupByWarehouse(report.entries);
  const notices = unmeasuredNotices(report.entries);

  return (
    <PageSection
      id="semana"
      title="Indicadores de la semana"
      description="Una fila por cliente en cada almacén. Las cifras no se suman entre clientes ni entre almacenes: cada fila es la operación de un cliente en un almacén."
    >
      <div className="space-y-5">
        <dl className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Semana ISO" value={shortWeekLabel(report.week_start)} detail="De lunes a domingo (UTC)" />
          <StatCard
            label="Clientes con actividad"
            value={entero(report.entries.length)}
            detail={groups.length ? `En ${groups.map((group) => group.name).join(" y ")}` : "Ningún almacén con actividad"}
          />
          <StatCard
            label="Datos calculados el"
            value={report.computed_at ? utcDateTime(report.computed_at).split(",")[0] : "—"}
            detail={report.computed_at ? `${utcDateTime(report.computed_at)} UTC` : undefined}
          />
        </dl>

        {report.entries.length === 0 ? (
          <p className={`${PANEL} text-sm text-slate-700`}>
            Semana calculada sin actividad: ningún almacén registró entradas, pedidos, quiebres ni discrepancias.
          </p>
        ) : (
          <>
            {groups.map((group) => (
              <WarehouseTable key={group.warehouse} name={group.name} entries={group.entries} />
            ))}
            {notices.length ? (
              <ul className="space-y-2 text-sm text-slate-700">
                {notices.map((notice) => (
                  <li key={notice} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-2">
                    <span aria-hidden="true">ⓘ </span>
                    {notice}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        )}
      </div>
    </PageSection>
  );
}

function WarehouseTable({ name, entries }: { name: string; entries: WeeklyPerformanceEntry[] }) {
  return (
    <>
      {/* Móvil: una tarjeta por cliente con los cuatro KPIs apilados (una tabla de 5 columnas no cabe). */}
      <section aria-label={`Almacén de ${name}`} className={`${PANEL} sm:hidden`}>
        <h3 className="font-heading text-lg text-slate-900">Almacén de {name}</h3>
        <ul className="mt-3 divide-y divide-slate-100">
          {entries.map((entry) => (
            <li key={entry.client_id} className="py-3">
              <p className="font-semibold text-slate-800">{entry.client_id}</p>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {KPIS.map((kpi) => (
                  <div key={kpi.key}>
                    <dt className="text-xs text-slate-500">{kpi.name}</dt>
                    <dd className="font-semibold tabular-nums text-slate-900">{formatKpi(entry, kpi.key)}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      </section>
      <WarehouseWideTable name={name} entries={entries} />
    </>
  );
}

function WarehouseWideTable({ name, entries }: { name: string; entries: WeeklyPerformanceEntry[] }) {
  return (
    <div className={`${PANEL} hidden overflow-x-auto sm:block`}>
      <table className="w-full min-w-[44rem] text-left text-sm">
        <caption className="mb-3 text-left font-heading text-lg text-slate-900">Almacén de {name}</caption>
        <thead>
          <tr className="align-bottom text-xs text-slate-500">
            <th scope="col" className="py-2 pr-3 font-semibold">
              Cliente
            </th>
            {KPIS.map((kpi) => (
              <th key={kpi.key} scope="col" className="px-3 py-2 text-right font-semibold">
                {kpi.name}
                <span className="block font-normal">({kpi.unit})</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.client_id} className="border-t border-slate-100 align-top">
              <th scope="row" className="py-3 pr-3 font-semibold whitespace-nowrap text-slate-800">
                {entry.client_id}
              </th>
              <td className="px-3 py-3 text-right tabular-nums">{entero(entry.inbound_units_count)}</td>
              <td className="px-3 py-3 text-right tabular-nums">{entero(entry.outbound_orders_count)}</td>
              <td className="px-3 py-3 text-right tabular-nums">{entero(entry.stockout_events_count)}</td>
              <td className="px-3 py-3">
                <RateMeter entry={entry} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Tasa de discrepancia: cifra, barra (escala 0–100 %) y el detalle que la explica. */
function RateMeter({ entry }: { entry: WeeklyPerformanceEntry }) {
  const width = Math.min(entry.discrepancy_rate, 1) * 100;
  const detail =
    entry.outbound_orders_count === 0
      ? entry.discrepancy_events_count > 0
        ? `${formatDiscrepancies(entry.discrepancy_events_count)} sin pedidos de salida (la tasa es 0 por definición)`
        : "Sin pedidos de salida"
      : `${formatDiscrepancies(entry.discrepancy_events_count)} en ${formatOrders(entry.outbound_orders_count)}`;
  return (
    <div className="ml-auto w-44 text-right">
      <p className="font-semibold tabular-nums text-slate-900">{formatRate(entry.discrepancy_rate)}</p>
      <div className="mt-1 h-1.5 rounded-full bg-slate-200" aria-hidden="true">
        <div className="h-full rounded-full bg-blue-700" style={{ width: `${width}%`, minWidth: width ? "4px" : 0 }} />
      </div>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
      {entry.discrepancy_rate > 1 ? (
        <p className="text-xs font-semibold text-slate-700">Más discrepancias que pedidos: revisar.</p>
      ) : null}
    </div>
  );
}

// --- Evolución -------------------------------------------------------------------------------------------------------

function History({ lastWeek }: { lastWeek: string }) {
  const [kpi, setKpi] = useState<KpiKey>("inbound");
  const request = useApiRequest(
    `history:${lastWeek}`,
    (signal) => weeklyPerformanceApi.history(lastWeek, HISTORY_WEEKS, signal),
    weeklyPerformanceErrorMessage
  );
  const { data: weeks, loading, reload } = request;
  const error = !loading ? request.error : null;
  const definition = KPIS.find((item) => item.key === kpi)!;
  const rows = weeks ? historyRows(weeks) : [];

  return (
    <PageSection
      id="evolucion"
      title="Evolución de las últimas semanas"
      description={`Cada indicador por almacén y cliente en las ${HISTORY_WEEKS} semanas que terminan en la semana elegida. Son los valores calculados de cada semana; las semanas sin calcular se indican y nunca se muestran como 0.`}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Indicador de la tabla de evolución">
          {KPIS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={kpi === item.key}
              onClick={() => setKpi(item.key)}
              className={`${BUTTON} ${kpi === item.key ? BUTTON_ACTIVE : BUTTON_IDLE}`}
            >
              {item.name}
            </button>
          ))}
        </div>

        {error ? (
          <LoadErrorAlert title="No se pudo cargar la evolución semanal." message={error} onRetry={reload} />
        ) : !weeks ? (
          <p role="status" className={`${PANEL} text-sm font-semibold text-slate-600`}>
            Cargando la evolución…
          </p>
        ) : rows.length === 0 ? (
          <p className={`${PANEL} text-sm text-slate-700`}>No hay actividad en ninguna de estas semanas.</p>
        ) : (
          <div className={`${PANEL} overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <p className="mb-2 text-xs text-slate-500 sm:hidden">Desliza la tabla en horizontal para ver todas las semanas.</p>
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="mb-3 text-left text-sm font-bold text-slate-700">
                {definition.name} ({definition.unit}) por semana
              </caption>
              <thead>
                <tr className="text-xs text-slate-500">
                  <th scope="col" className="py-2 pr-3 font-semibold">
                    Almacén · cliente
                  </th>
                  {weeks.map(({ weekStart, report }) => (
                    <th
                      key={weekStart}
                      scope="col"
                      className={`px-2 py-2 text-right font-semibold ${weekStart === lastWeek ? "text-blue-800" : ""}`}
                    >
                      {shortWeekLabel(weekStart)}
                      {report === null ? <span className="block font-normal">sin calcular</span> : null}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="border-t border-slate-100">
                    <th scope="row" className="py-2 pr-3 font-semibold whitespace-nowrap text-slate-800">
                      {warehouseName(row.warehouse)} · {row.clientId}
                    </th>
                    {row.cells.map((cell, index) => (
                      <td key={weeks[index].weekStart} className="px-2 py-2 text-right tabular-nums">
                        {cell === "not_computed" ? (
                          <span className="text-slate-400" title="Semana sin calcular">
                            ·
                          </span>
                        ) : cell === "inactive" ? (
                          <span className="text-slate-400" title="Sin actividad de este cliente esa semana">
                            —
                          </span>
                        ) : (
                          historyValue(cell, kpi)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-slate-500">
              «—»: semana calculada sin actividad de ese cliente en ese almacén. «·»: semana sin calcular.
            </p>
          </div>
        )}
      </div>
    </PageSection>
  );
}

function historyValue(entry: WeeklyPerformanceEntry, kpi: KpiKey): string {
  switch (kpi) {
    case "inbound":
      return entero(entry.inbound_units_count);
    case "outbound":
      return entero(entry.outbound_orders_count);
    case "stockout":
      return entero(entry.stockout_events_count);
    case "discrepancy":
      return formatRate(entry.discrepancy_rate);
  }
}

// --- Definiciones ----------------------------------------------------------------------------------------------------

function KpiDefinitions() {
  return (
    <PageSection
      id="como-leer"
      title="Cómo leer los indicadores"
      description="Definiciones del Reporte Semanal de Desempeño por Almacén y Cliente. Cada cifra corresponde a un cliente en un almacén durante una semana."
    >
      <dl className="grid gap-4 sm:grid-cols-2">
        {KPIS.map((kpi) => (
          <div key={kpi.key} className={PANEL}>
            <dt className="font-bold text-slate-900">
              {kpi.name} <span className="font-normal text-slate-500">({kpi.unit})</span>
            </dt>
            <dd className="mt-1 text-sm text-slate-600">
              {kpi.description}
              {kpi.key === "discrepancy"
                ? " Se calcula como discrepancias detectadas ÷ pedidos de salida; si no hubo pedidos, es 0. Puede superar el 100 %."
                : null}
            </dd>
          </div>
        ))}
      </dl>
    </PageSection>
  );
}
