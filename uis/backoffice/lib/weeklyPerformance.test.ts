/**
 * Utilidades del dashboard `/reporting` (`lib/weeklyPerformance.ts`): llamadas a `GET /reporting/...`, semanas ISO en
 * UTC, formato de los KPIs, agrupación por almacén, tabla de evolución y avisos de KPIs sin medir.
 *
 * `fetch` se sustituye por un doble con respuestas de la misma forma que la API real (`services/api/app/reporting`).
 */
import type * as WeeklyPerformanceModule from "@/lib/weeklyPerformance";
import { TOKEN_KEY } from "@/lib/session";
import type { WeeklyPerformanceEntry, WeeklyPerformanceReport } from "@/types/weeklyPerformance";

const entry = (overrides: Partial<WeeklyPerformanceEntry>): WeeklyPerformanceEntry => ({
  warehouse: "los_angeles",
  client_id: "fashion-co",
  inbound_units_count: 600,
  outbound_orders_count: 8,
  stockout_events_count: 1,
  discrepancy_events_count: 2,
  discrepancy_rate: 0.25,
  ...overrides,
});

const REPORT: WeeklyPerformanceReport = {
  week_start: "2026-11-02",
  computed_at: "2026-11-14T18:39:42.792597Z",
  run_id: "f466a40f-3e69-409b-8119-f9f6e51353db",
  entries: [
    entry({ warehouse: "zaragoza", client_id: "home-plus" }),
    entry({ client_id: "tech-gear" }),
    entry({}),
  ],
};

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: jest.Mock;

async function load() {
  jest.resetModules();
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  const reporting: typeof WeeklyPerformanceModule = await import("@/lib/weeklyPerformance");
  const http = await import("@/lib/http");
  return { ...reporting, ApiError: http.ApiError };
}

beforeEach(() => {
  const storage = new Map([[TOKEN_KEY, "token-de-prueba"]]);
  Object.defineProperty(globalThis, "window", {
    value: {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => void storage.set(key, value),
        removeItem: (key: string) => void storage.delete(key),
      },
      dispatchEvent: () => true,
    },
    configurable: true,
    writable: true,
  });
  fetchMock = jest.fn();
  global.fetch = fetchMock;
});

afterAll(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe("weeklyPerformanceApi", () => {
  it("pide la semana más reciente sin parámetros y con el token de la sesión", async () => {
    const { weeklyPerformanceApi } = await load();
    fetchMock.mockResolvedValue(json(200, REPORT));
    await expect(weeklyPerformanceApi.get(null)).resolves.toEqual(REPORT);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/reporting/weekly-warehouse-client-performance");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-de-prueba");
  });

  it("pide una semana concreta con week_start", async () => {
    const { weeklyPerformanceApi } = await load();
    fetchMock.mockResolvedValue(json(200, REPORT));
    await weeklyPerformanceApi.get("2026-10-26");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://api.test/reporting/weekly-warehouse-client-performance?week_start=2026-10-26"
    );
  });

  it("un 404 es «semana sin calcular» (null), no un error", async () => {
    const { weeklyPerformanceApi } = await load();
    fetchMock.mockResolvedValue(json(404, { detail: "Aún no hay ninguna semana calculada: ejecuta el pipeline" }));
    await expect(weeklyPerformanceApi.get(null)).resolves.toBeNull();
  });

  it("la evolución pide cada semana, de la más antigua a la más reciente, y marca las no calculadas", async () => {
    const { weeklyPerformanceApi } = await load();
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith("2026-10-26") ? json(404, { detail: "no calculada" }) : json(200, REPORT)
    );
    const weeks = await weeklyPerformanceApi.history("2026-11-02", 3);
    expect(weeks.map((week) => [week.weekStart, week.report === null])).toEqual([
      ["2026-10-19", false],
      ["2026-10-26", true],
      ["2026-11-02", false],
    ]);
  });

  it("los errores del servidor no muestran detalles técnicos", async () => {
    const { weeklyPerformanceApi, weeklyPerformanceErrorMessage } = await load();
    fetchMock.mockResolvedValue(json(503, { detail: "No se ha podido leer la tabla reporting.weekly_..." }));
    const error = await weeklyPerformanceApi.get(null).catch((caught: unknown) => caught);
    const message = weeklyPerformanceErrorMessage(error);
    expect(message).toBe(
      "No se ha podido cargar el reporte semanal por un problema del servidor. Inténtalo de nuevo en unos minutos."
    );
    expect(message).not.toMatch(/reporting|tabla|503/);
  });

  it("la última ejecución es null si el pipeline nunca se ha ejecutado", async () => {
    const { weeklyPerformanceApi } = await load();
    fetchMock.mockResolvedValue(json(404, { detail: "nunca" }));
    await expect(weeklyPerformanceApi.latestRun()).resolves.toBeNull();
  });
});

describe("semanas ISO (UTC)", () => {
  it("suma días y calcula el número de semana ISO", async () => {
    const { addDays, isoWeekNumber } = await load();
    expect(addDays("2026-11-02", 7)).toBe("2026-11-09");
    expect(addDays("2026-11-02", -7)).toBe("2026-10-26");
    expect(addDays("2026-03-30", -7)).toBe("2026-03-23"); // cambio de hora en Europa: sin efecto en UTC
    expect(isoWeekNumber("2026-11-02")).toBe(45);
    expect(isoWeekNumber("2025-12-29")).toBe(1); // la semana 1 de 2026 empieza en 2025
    expect(isoWeekNumber("2026-12-28")).toBe(53);
  });

  it("describe el período de lunes a domingo y separa la fecha de cálculo", async () => {
    const { weekPeriodLabel, shortWeekLabel, utcDateTime } = await load();
    expect(weekPeriodLabel("2026-11-02")).toBe("Semana 45 · del lunes 2 nov al domingo 8 nov 2026");
    expect(shortWeekLabel("2026-11-02")).toBe("S45 · 2 nov");
    expect(utcDateTime("2026-11-14T18:39:42.792597Z")).toBe("14 nov 2026, 18:39");
  });
});

describe("frescura del reporte", () => {
  it("la última semana completa es la anterior a la semana en curso (UTC)", async () => {
    const { lastCompleteWeek } = await load();
    expect(lastCompleteWeek(new Date("2026-11-14T12:00:00Z"))).toBe("2026-11-02"); // sábado
    expect(lastCompleteWeek(new Date("2026-11-16T00:00:00Z"))).toBe("2026-11-09"); // lunes 00:00 UTC
    expect(lastCompleteWeek(new Date("2026-11-15T23:59:59Z"))).toBe("2026-11-02"); // domingo 23:59:59 UTC
  });

  it("cuenta las semanas completas que faltan por calcular", async () => {
    const { weeksBehind } = await load();
    const saturday = new Date("2026-11-14T12:00:00Z");
    expect(weeksBehind("2026-11-02", saturday)).toBe(0);
    expect(weeksBehind("2026-10-19", saturday)).toBe(2);
    expect(weeksBehind("2026-11-02", new Date("2026-11-17T08:00:00Z"))).toBe(1); // el lunes siguiente sin cálculo
  });
});

describe("formato de los KPIs", () => {
  it("muestra cada KPI con su unidad", async () => {
    const { formatKpi, formatRate } = await load();
    const row = entry({ inbound_units_count: 1324, outbound_orders_count: 1, stockout_events_count: 2 });
    expect(formatKpi(row, "inbound")).toBe("1324 unidades");
    expect(formatKpi(row, "outbound")).toBe("1 pedido");
    expect(formatKpi(row, "stockout")).toBe("2 veces");
    expect(formatKpi(row, "discrepancy")).toBe("25 %");
    expect(formatRate(0.3333)).toBe("33,33 %");
    expect(formatRate(1.5)).toBe("150 %");
    expect(formatRate(0)).toBe("0 %");
  });

  it("usa los nombres exactos de los KPIs del BRIEFING", async () => {
    const { KPIS } = await load();
    expect(KPIS.map((kpi) => kpi.name)).toEqual([
      "Volumen de entrada",
      "Throughput de salida",
      "Frecuencia de quiebre de stock",
      "Tasa de discrepancia",
    ]);
  });
});

describe("organización de las filas", () => {
  it("agrupa por almacén (Los Ángeles primero) y ordena por cliente, sin sumar nada", async () => {
    const { groupByWarehouse } = await load();
    const groups = groupByWarehouse(REPORT.entries);
    expect(groups.map((group) => [group.name, group.entries.map((row) => row.client_id)])).toEqual([
      ["Los Ángeles", ["fashion-co", "tech-gear"]],
      ["Zaragoza", ["home-plus"]],
    ]);
    expect(groups[0].entries[0]).toBe(REPORT.entries[2]); // las mismas filas de la API, sin transformar
  });

  it("la evolución distingue semana sin calcular de semana sin actividad", async () => {
    const { historyRows } = await load();
    const rows = historyRows([
      { weekStart: "2026-10-26", report: null },
      { weekStart: "2026-11-02", report: { ...REPORT, entries: [entry({})] } },
      { weekStart: "2026-11-09", report: { ...REPORT, week_start: "2026-11-09", entries: [] } },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].cells[0]).toBe("not_computed");
    expect(rows[0].cells[1]).toMatchObject({ inbound_units_count: 600 });
    expect(rows[0].cells[2]).toBe("inactive");
  });

  it("avisa de los KPIs que pueden estar sin medir solo si ninguna fila los tiene", async () => {
    const { unmeasuredNotices } = await load();
    const quiet = [entry({ stockout_events_count: 0, discrepancy_events_count: 0, discrepancy_rate: 0 })];
    expect(unmeasuredNotices(quiet)).toHaveLength(2);
    expect(unmeasuredNotices(REPORT.entries)).toEqual([]);
    expect(unmeasuredNotices([])).toEqual([]);
  });
});
