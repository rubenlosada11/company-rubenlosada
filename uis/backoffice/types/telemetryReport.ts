/** Respuesta de `GET /telemetry/report` (`services/api/app/telemetry/report.py`). Fechas de día en UTC. */

export interface DailyEvents {
  date: string;
  total_events: number;
}

export interface ErrorsByType {
  error_category: string;
  event_type: string;
  reason: string | null;
  errors: number;
  share_pct: number | null;
}

export interface DailyErrors {
  date: string;
  errors: number;
}

export interface DailyAuthFailureRate {
  date: string;
  failed: number;
  succeeded: number;
  attempts: number;
  failure_rate_pct: number | null;
}

export interface FormSubmissionFailures {
  form_id: string | null;
  submissions: number;
  failed: number;
  failure_rate_pct: number | null;
}

export interface TelemetryReport {
  period: { from: string; to: string };
  metrics: {
    events_per_day: DailyEvents[];
    error_rate_by_type: ErrorsByType[];
    errors_per_day: DailyErrors[];
    auth_failure_rate: DailyAuthFailureRate[];
    submission_failures_by_form: FormSubmissionFailures[];
  };
}
