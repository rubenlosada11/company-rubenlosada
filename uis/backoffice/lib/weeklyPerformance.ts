/**
 * Reporte Semanal de Desempeño por Almacén y Cliente (`GET /reporting/...` de `services/api`): llamadas y utilidades
 * de presentación del dashboard `/reporting`.
 *
 * Los KPIs los calcula el pipeline semanal (`data/pipelines/pipeline.py`) y los sirve la API desde la tabla
 * `reporting.weekly_warehouse_client_performance`. Aquí **no se calcula ningún KPI**: solo se piden, se ordenan y se
 * formatean. Los nombres de los indicadores son los del BRIEFING (`CONTEXT-datapipelines.es.md` §2).
 */
import { ApiError, apiErrorMessage, http } from "@/lib/http";
import type {
  PipelineRunSummary,
  Warehouse,
  WeeklyPerformanceEntry,
  WeeklyPerformanceReport,
  WeekReport,
} from "@/types/weeklyPerformance";

const REPORT_PATH = "/reporting/weekly-warehouse-client-performance";
const LATEST_RUN_PATH = "/reporting/pipeline-runs/latest";
const DAY_MS = 86_400_000;

/** Semanas de la tabla de evolución (incluida la que se está viendo). */
export const HISTORY_WEEKS = 6;

export type KpiKey = "inbound" | "outbound" | "stockout" | "discrepancy";

export interface KpiDefinition {
  key: KpiKey;
  /** Nombre exacto del KPI en el BRIEFING. */
  name: string;
  /** Unidad, en plural, para las cabeceras. */
  unit: string;
  /** Qué mide, en lenguaje de negocio. */
  description: string;
}

/** Los cuatro KPIs del BRIEFING (§2), en su orden. */
export const KPIS: readonly KpiDefinition[] = [
  {
    key: "inbound",
    name: "Volumen de entrada",
    unit: "unidades",
    description: "Unidades de mercancía del cliente que recibió el almacén durante la semana.",
  },
  {
    key: "outbound",
    name: "Throughput de salida",
    unit: "pedidos",
    description: "Pedidos que el almacén preparó y despachó para el cliente durante la semana.",
  },
  {
    key: "stockout",
    name: "Frecuencia de quiebre de stock",
    unit: "veces",
    description: "Veces que un SKU del cliente en el almacén cayó por debajo del mínimo configurado.",
  },
  {
    key: "discrepancy",
    name: "Tasa de discrepancia",
    unit: "%",
    description: "Proporción de los pedidos de salida de la semana asociados a una discrepancia de inventario.",
  },
] as const;

const WAREHOUSE_NAMES: Record<Warehouse, string> = { los_angeles: "Los Ángeles", zaragoza: "Zaragoza" };
const WAREHOUSE_ORDER: Warehouse[] = ["los_angeles", "zaragoza"];

export function warehouseName(warehouse: string): string {
  return WAREHOUSE_NAMES[warehouse as Warehouse] ?? warehouse;
}

// --- Llamadas a la API -----------------------------------------------------------------------------------------------

/** `null` si la API responde 404: la semana (o ninguna, sin `weekStart`) aún no se ha calculado. No es un error. */
async function getReport(weekStart: string | null, signal?: AbortSignal): Promise<WeeklyPerformanceReport | null> {
  const query = weekStart ? `?${new URLSearchParams({ week_start: weekStart })}` : "";
  try {
    return await http.get<WeeklyPerformanceReport>(`${REPORT_PATH}${query}`, signal);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export const weeklyPerformanceApi = {
  /** Reporte de la semana `weekStart` (un lunes) o, sin ella, de la semana calculada más reciente. */
  get: getReport,

  /** Las `count` semanas que terminan en `lastWeek`, de la más antigua a la más reciente, con su reporte o `null`. */
  async history(lastWeek: string, count: number = HISTORY_WEEKS, signal?: AbortSignal): Promise<WeekReport[]> {
    const weeks = Array.from({ length: count }, (_, index) => addDays(lastWeek, -7 * (count - 1 - index)));
    const reports = await Promise.all(weeks.map((week) => getReport(week, signal)));
    return weeks.map((weekStart, index) => ({ weekStart, report: reports[index] }));
  },

  /** Última ejecución del pipeline (`null` si nunca se ha ejecutado). */
  async latestRun(signal?: AbortSignal): Promise<PipelineRunSummary | null> {
    try {
      return await http.get<PipelineRunSummary>(LATEST_RUN_PATH, signal);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
};

/** Mensaje para la persona que consulta el reporte: nunca rutas, tablas ni códigos HTTP. */
export function weeklyPerformanceErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) {
    return "La semana pedida no es válida. Vuelve a la semana más reciente.";
  }
  return apiErrorMessage(error, "cargar el reporte semanal");
}

// --- Semanas (UTC) ---------------------------------------------------------------------------------------------------

function parseDay(day: string): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date));
}

function formatDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Lunes (UTC) de la última semana ISO **terminada** respecto a `now`: la más reciente que el pipeline puede calcular. */
export function lastCompleteWeek(now: Date = new Date()): string {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const mondayThisWeek = today - ((now.getUTCDay() + 6) % 7) * DAY_MS;
  return formatDay(new Date(mondayThisWeek - 7 * DAY_MS));
}

/**
 * Semanas completas que faltan por calcular después de `latestComputed` (0 = el reporte está al día). Es una
 * comparación de fechas para avisar de que el dato no está fresco (PIPELINE_DESIGN §19.9), no un cálculo de KPIs.
 */
export function weeksBehind(latestComputed: string, now: Date = new Date()): number {
  const behind = (parseDay(lastCompleteWeek(now)).getTime() - parseDay(latestComputed).getTime()) / (7 * DAY_MS);
  return Math.max(0, Math.round(behind));
}

/** «2026-11-02» + 7 → «2026-11-09» (días naturales en UTC). */
export function addDays(day: string, days: number): string {
  return formatDay(new Date(parseDay(day).getTime() + days * DAY_MS));
}

/** Número de semana ISO 8601 del lunes `weekStart`. */
export function isoWeekNumber(weekStart: string): number {
  const thursday = parseDay(addDays(weekStart, 3));
  const firstThursday = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 4));
  const firstMonday = firstThursday.getTime() - ((firstThursday.getUTCDay() + 6) % 7) * DAY_MS;
  return Math.floor((thursday.getTime() - firstMonday) / (7 * DAY_MS)) + 1;
}

const DAY_MONTH = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });
const DAY_MONTH_YEAR = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const INSTANT = new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/** «Semana 45 · del lunes 2 nov al domingo 8 nov 2026» (semana ISO, UTC). */
export function weekPeriodLabel(weekStart: string): string {
  const sunday = addDays(weekStart, 6);
  return `Semana ${isoWeekNumber(weekStart)} · del lunes ${DAY_MONTH.format(parseDay(weekStart))} al domingo ${DAY_MONTH_YEAR.format(parseDay(sunday))}`;
}

/** «2 nov» para las cabeceras de la tabla de evolución. */
export function shortWeekLabel(weekStart: string): string {
  return `S${isoWeekNumber(weekStart)} · ${DAY_MONTH.format(parseDay(weekStart))}`;
}

/** Instante ISO → «14 nov 2026, 18:39» (UTC). */
export function utcDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : INSTANT.format(date);
}

// --- Formato de los valores ------------------------------------------------------------------------------------------

const INTEGER = new Intl.NumberFormat("es-ES");
const PERCENT = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

function plural(count: number, singular: string, pluralForm: string): string {
  return `${INTEGER.format(count)} ${count === 1 ? singular : pluralForm}`;
}

export const formatUnits = (count: number) => plural(count, "unidad", "unidades");
export const formatOrders = (count: number) => plural(count, "pedido", "pedidos");
export const formatTimes = (count: number) => plural(count, "vez", "veces");
export const formatDiscrepancies = (count: number) => plural(count, "discrepancia", "discrepancias");

/** 0,25 → «25 %»; 0,3333 → «33,33 %». La tasa llega con 4 decimales de la API. */
export function formatRate(rate: number): string {
  return `${PERCENT.format(rate * 100)} %`;
}

/** Valor formateado de un KPI de una fila, con su unidad. */
export function formatKpi(entry: WeeklyPerformanceEntry, kpi: KpiKey): string {
  switch (kpi) {
    case "inbound":
      return formatUnits(entry.inbound_units_count);
    case "outbound":
      return formatOrders(entry.outbound_orders_count);
    case "stockout":
      return formatTimes(entry.stockout_events_count);
    case "discrepancy":
      return formatRate(entry.discrepancy_rate);
  }
}

// --- Organización de las filas ---------------------------------------------------------------------------------------

export interface WarehouseGroup {
  warehouse: Warehouse;
  name: string;
  entries: WeeklyPerformanceEntry[];
}

/** Filas agrupadas por almacén (Los Ángeles, Zaragoza) y ordenadas por cliente. Cada fila sigue siendo de un cliente. */
export function groupByWarehouse(entries: WeeklyPerformanceEntry[]): WarehouseGroup[] {
  return WAREHOUSE_ORDER.map((warehouse) => ({
    warehouse,
    name: warehouseName(warehouse),
    entries: entries
      .filter((entry) => entry.warehouse === warehouse)
      .sort((a, b) => a.client_id.localeCompare(b.client_id)),
  })).filter((group) => group.entries.length > 0);
}

/** Clave estable de una combinación almacén/cliente. */
export function comboKey(entry: Pick<WeeklyPerformanceEntry, "warehouse" | "client_id">): string {
  return `${entry.warehouse}/${entry.client_id}`;
}

export interface HistoryRow {
  key: string;
  warehouse: string;
  clientId: string;
  /** Una celda por semana de `weeks`: la fila de esa semana, `"inactive"` (semana calculada sin actividad de esta
   * combinación) o `"not_computed"` (semana sin calcular). */
  cells: (WeeklyPerformanceEntry | "inactive" | "not_computed")[];
}

/** Tabla de evolución: una fila por combinación que aparece en alguna de las semanas, por almacén y cliente. */
export function historyRows(weeks: WeekReport[]): HistoryRow[] {
  const combos = new Map<string, { warehouse: string; clientId: string }>();
  for (const { report } of weeks) {
    for (const entry of report?.entries ?? []) {
      combos.set(comboKey(entry), { warehouse: entry.warehouse, clientId: entry.client_id });
    }
  }
  const order = (warehouse: string) => WAREHOUSE_ORDER.indexOf(warehouse as Warehouse);
  return [...combos.entries()]
    .sort(([, a], [, b]) => order(a.warehouse) - order(b.warehouse) || a.clientId.localeCompare(b.clientId))
    .map(([key, combo]) => ({
      key,
      ...combo,
      cells: weeks.map(({ report }) =>
        report === null ? "not_computed" : (report.entries.find((entry) => comboKey(entry) === key) ?? "inactive")
      ),
    }));
}

/**
 * Avisos sobre KPIs que hoy pueden estar «sin medir» (PIPELINE_DESIGN §4.1): si ninguna fila de la semana tiene
 * quiebres o discrepancias, un 0 no garantiza que no los hubiera. Se basa solo en los datos recibidos.
 */
export function unmeasuredNotices(entries: WeeklyPerformanceEntry[]): string[] {
  if (entries.length === 0) return [];
  const notices: string[] = [];
  if (entries.every((entry) => entry.stockout_events_count === 0)) {
    notices.push(
      "Frecuencia de quiebre de stock: ningún almacén registró quiebres esta semana. Mientras no estén configurados los mínimos de stock por cliente, este indicador no se puede medir y aparece a 0."
    );
  }
  if (entries.every((entry) => entry.discrepancy_events_count === 0)) {
    notices.push(
      "Tasa de discrepancia: no se registró ninguna discrepancia esta semana. Mientras no exista un proceso de conteo físico del inventario, las discrepancias no se detectan y la tasa aparece a 0."
    );
  }
  return notices;
}
