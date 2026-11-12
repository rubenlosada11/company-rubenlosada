import {
  errorCategoryLabel,
  errorTypeLabel,
  longDay,
  reportPeriod,
  reportTotals,
  shortDay,
  showAxisLabel,
  utcInstant,
} from "@/lib/telemetryReport";
import type { TelemetryReport } from "@/types/telemetryReport";

const REPORT: TelemetryReport = {
  period: { from: "2026-11-04T21:25:00Z", to: "2026-11-11T21:25:00Z" },
  metrics: {
    events_per_day: [
      { date: "2026-11-10", total_events: 0 },
      { date: "2026-11-11", total_events: 31 },
    ],
    error_rate_by_type: [
      {
        error_category: "authentication",
        event_type: "login_failed",
        reason: "invalid_credentials",
        errors: 1,
        share_pct: 50,
      },
      { error_category: "validation", event_type: "form_validation_failed", reason: null, errors: 1, share_pct: 50 },
    ],
    errors_per_day: [
      { date: "2026-11-10", errors: 0 },
      { date: "2026-11-11", errors: 2 },
    ],
    auth_failure_rate: [{ date: "2026-11-11", failed: 1, succeeded: 1, attempts: 2, failure_rate_pct: 50 }],
    submission_failures_by_form: [
      { form_id: "login", submissions: 2, failed: 1, failure_rate_pct: 50 },
      { form_id: "inventory_inbound", submissions: 2, failed: 0, failure_rate_pct: 0 },
    ],
  },
};

describe("reportPeriod", () => {
  it("termina en el minuto siguiente (UTC) y empieza los días pedidos antes", () => {
    const now = new Date("2026-11-11T21:24:37.512Z");
    expect(reportPeriod(7, now)).toEqual({ from: "2026-11-04T21:25:00.000Z", to: "2026-11-11T21:25:00.000Z" });
    expect(reportPeriod(30, now).from).toBe("2026-10-12T21:25:00.000Z");
  });

  it("da el mismo periodo a todas las peticiones del mismo minuto (caché del servidor)", () => {
    expect(reportPeriod(7, new Date("2026-11-11T21:24:00.000Z"))).toEqual(
      reportPeriod(7, new Date("2026-11-11T21:24:59.999Z"))
    );
  });
});

describe("reportTotals", () => {
  it("suma las métricas del periodo", () => {
    expect(reportTotals(REPORT)).toEqual({
      events: 31,
      errors: 2,
      loginFailed: 1,
      loginAttempts: 2,
      loginFailureRate: 50,
      submissions: 4,
      failedSubmissions: 1,
    });
  });

  it("no divide entre cero sin intentos de login", () => {
    const empty: TelemetryReport = {
      ...REPORT,
      metrics: { ...REPORT.metrics, auth_failure_rate: [], submission_failures_by_form: [] },
    };
    expect(reportTotals(empty)).toMatchObject({ loginAttempts: 0, loginFailureRate: null, submissions: 0 });
  });
});

describe("etiquetas y fechas", () => {
  it("traduce las categorías conocidas y deja las desconocidas como vienen", () => {
    expect(errorCategoryLabel("authentication")).toBe("Autenticación");
    expect(errorCategoryLabel("nueva_categoria")).toBe("nueva_categoria");
  });

  it("compone la etiqueta de un tipo de incidencia sin motivo nulo", () => {
    expect(errorTypeLabel(REPORT.metrics.error_rate_by_type[0])).toBe(
      "Autenticación · login_failed · invalid_credentials"
    );
    expect(errorTypeLabel(REPORT.metrics.error_rate_by_type[1])).toBe("Validación · form_validation_failed");
  });

  it("rotula todos los días de «7 días» (8 fechas) y como mucho 8 de «30 días», siempre el último", () => {
    const labelled = (count: number) => [...Array(count).keys()].filter((index) => showAxisLabel(index, count));
    expect(labelled(8)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(labelled(31)).toEqual([2, 6, 10, 14, 18, 22, 26, 30]);
    expect(labelled(30)).toEqual([1, 5, 9, 13, 17, 21, 25, 29]);
    expect(labelled(9)).toEqual([0, 2, 4, 6, 8]);
    expect(labelled(1)).toEqual([0]);
  });

  it("formatea días e instantes en UTC y no rompe con valores no válidos", () => {
    expect(shortDay("2026-11-01")).toBe("01/11");
    expect(longDay("2026-11-01")).toMatch(/1 nov 2026/);
    expect(utcInstant("2026-11-11T21:25:00Z")).toMatch(/11 nov 2026.*21:25/);
    expect(shortDay("no-es-fecha")).toBe("no-es-fecha");
  });
});
