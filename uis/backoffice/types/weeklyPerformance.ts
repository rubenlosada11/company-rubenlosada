/**
 * Respuestas de `/reporting` (`services/api/app/reporting/models.py`): Reporte Semanal de Desempeño por Almacén y
 * Cliente. Contrato del BRIEFING (`CONTEXT-datapipelines.es.md` §6) más `computed_at` y `run_id`. Fechas en UTC.
 */

export type Warehouse = "los_angeles" | "zaragoza";

/** Una fila del reporte: un almacén y un cliente en la semana. Los valores los calcula el pipeline. */
export interface WeeklyPerformanceEntry {
  warehouse: Warehouse;
  client_id: string;
  inbound_units_count: number;
  outbound_orders_count: number;
  stockout_events_count: number;
  discrepancy_events_count: number;
  /** discrepancy_events_count / outbound_orders_count (0 sin pedidos; puede superar 1). */
  discrepancy_rate: number;
}

/** `GET /reporting/weekly-warehouse-client-performance`. */
export interface WeeklyPerformanceReport {
  /** Lunes de la semana ISO (`YYYY-MM-DD`). */
  week_start: string;
  /** Fin de la ejecución que calculó la semana (ISO 8601 UTC). */
  computed_at: string | null;
  run_id: string | null;
  entries: WeeklyPerformanceEntry[];
}

/** `GET /reporting/pipeline-runs/latest` (solo los campos que usa la vista). */
export interface PipelineRunSummary {
  status: "running" | "succeeded" | "failed";
  outcome: "running" | "succeeded" | "partial" | "failed";
  week_from: string;
  week_to: string;
  started_at: string;
  finished_at: string | null;
}

/** Una semana de la evolución: su reporte, o `null` si ninguna ejecución correcta la ha calculado. */
export interface WeekReport {
  weekStart: string;
  report: WeeklyPerformanceReport | null;
}
