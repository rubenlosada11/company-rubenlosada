/**
 * Reporte técnico de telemetría (`GET /telemetry/report` de `services/api`): llamada y utilidades de presentación.
 *
 * Las métricas las calcula la API (SQL + Pandas); aquí solo se piden y se resumen para la vista. El periodo termina en
 * el minuto siguiente al actual, como el de la API sin parámetros, para que las peticiones del mismo minuto compartan
 * la caché de 60 s del servidor.
 */
import { apiErrorMessage, http } from "@/lib/http";
import type { TelemetryReport } from "@/types/telemetryReport";

const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

export const REPORT_PERIODS = [
  { days: 7, label: "Últimos 7 días" },
  { days: 30, label: "Últimos 30 días" },
] as const;

export type ReportDays = (typeof REPORT_PERIODS)[number]["days"];

/** `[from, to)` en ISO 8601 UTC: `to` es el minuto siguiente a `now` y `from`, `days` días antes. */
export function reportPeriod(days: number, now: Date = new Date()): { from: string; to: string } {
  const to = Math.floor(now.getTime() / MINUTE_MS) * MINUTE_MS + MINUTE_MS;
  return { from: new Date(to - days * DAY_MS).toISOString(), to: new Date(to).toISOString() };
}

export const telemetryReportApi = {
  get(days: number, signal?: AbortSignal, now?: Date): Promise<TelemetryReport> {
    const { from, to } = reportPeriod(days, now);
    const query = new URLSearchParams({ start_date: from, end_date: to });
    return http.get<TelemetryReport>(`/telemetry/report?${query}`, signal);
  },
};

export function telemetryReportErrorMessage(error: unknown): string {
  return apiErrorMessage(error, "cargar el reporte de telemetría");
}

/** Categorías de incidencia de la API (`ERROR_EVENT_TYPES` de `analysis.py`), en español. */
const ERROR_CATEGORY_LABELS: Record<string, string> = {
  authentication: "Autenticación",
  authorization: "Autorización",
  validation: "Validación",
  frontend: "Errores del frontend",
  api_communication: "Comunicación con la API",
  server: "Servidor",
  database: "Base de datos",
  telemetry: "Pérdida de telemetría",
};

export function errorCategoryLabel(category: string): string {
  return ERROR_CATEGORY_LABELS[category] ?? category;
}

/** Totales del periodo para las tarjetas de la cabecera. Los porcentajes son `null` si no hay intentos o envíos. */
export function reportTotals(report: TelemetryReport) {
  const { metrics } = report;
  const sum = <T>(rows: T[], value: (row: T) => number) => rows.reduce((total, row) => total + value(row), 0);
  const events = sum(metrics.events_per_day, (row) => row.total_events);
  const errors = sum(metrics.errors_per_day, (row) => row.errors);
  const loginFailed = sum(metrics.auth_failure_rate, (row) => row.failed);
  const loginAttempts = sum(metrics.auth_failure_rate, (row) => row.attempts);
  const submissions = sum(metrics.submission_failures_by_form, (row) => row.submissions);
  const failedSubmissions = sum(metrics.submission_failures_by_form, (row) => row.failed);
  return {
    events,
    errors,
    loginFailed,
    loginAttempts,
    loginFailureRate: loginAttempts ? (loginFailed * 100) / loginAttempts : null,
    submissions,
    failedSubmissions,
  };
}

/** Clave legible de una fila de incidencias: «Autenticación · login_failed · invalid_credentials». */
export function errorTypeLabel(row: { error_category: string; event_type: string; reason: string | null }): string {
  return [errorCategoryLabel(row.error_category), row.event_type, row.reason].filter(Boolean).join(" · ");
}

const DAY_LONG = new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeZone: "UTC" });
const INSTANT = new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

function parse(value: string): Date | null {
  const date = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** «2026-11-01» → «01/11» (día UTC, para el eje). Sin `Intl`: su `2-digit` no es igual en todos los navegadores. */
export function shortDay(value: string): string {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[2]}/${match[1]}` : value;
}

/** «2026-11-11» → «11 nov 2026» (día UTC). */
export function longDay(value: string): string {
  const date = parse(value);
  return date ? DAY_LONG.format(date) : value;
}

/** Instante ISO → «11 nov 2026, 21:25» en UTC. */
export function utcInstant(value: string): string {
  const date = parse(value);
  return date ? INSTANT.format(date) : value;
}
