/**
 * FE-019 — utilidades del directorio de proveedores (`lib/suppliers.ts`). Ver TESTING.md §10.
 *
 * Reglas del CONTEXT (`CONTEXT-directorio.md`) que replica el formulario: tarifa > 0, moneda fijada por el país, al
 * menos una categoría y email con formato básico. Las claves de `errors` son los campos de la API.
 */
import { EMPTY_DRAFT, formatDateTime, formatRate, parseRate, validateDraft, type SupplierDraft } from "@/lib/suppliers";

/** `Intl` separa número y símbolo con un espacio no separable: se normaliza para comparar. */
const plain = (text: string) => text.replace(/\s/g, " ");

const VALID: SupplierDraft = {
  ...EMPTY_DRAFT,
  name: "  MRW España  ",
  country: "Spain",
  categories: ["carrier_last_mile"],
  rate: "7,45",
};

describe("parseRate", () => {
  it.each([
    ["7.45", 7.45],
    ["7,45", 7.45],
    ["  12  ", 12],
    ["0.01", 0.01],
  ])("convierte %p en %p", (input, expected) => {
    expect(parseRate(input)).toBe(expected);
  });

  it.each(["", "   ", "0", "-3", "abc", "7,4,5", "Infinity", "1e400"])("rechaza %p", (input) => {
    expect(parseRate(input)).toBeNull();
  });
});

describe("validateDraft", () => {
  it("con datos válidos construye el payload de la API con la moneda del país", () => {
    const { payload, errors } = validateDraft(VALID);
    expect(errors).toEqual({});
    expect(payload).toEqual({
      name: "MRW España",
      country: "Spain",
      categories: ["carrier_last_mile"],
      rate_per_shipment: 7.45,
      currency: "EUR",
      status: "active",
      service_zone: null,
      contact_email: null,
      notes: null,
    });
  });

  it("un proveedor de USA lleva USD y los opcionales en blanco van como null", () => {
    const { payload } = validateDraft({ ...VALID, country: "USA", service_zone: "  ", notes: "", contact_email: " " });
    expect(payload).toMatchObject({ currency: "USD", service_zone: null, notes: null, contact_email: null });
  });

  it("con el borrador vacío señala cada campo obligatorio con la clave de la API", () => {
    const { payload, errors } = validateDraft(EMPTY_DRAFT);
    expect(payload).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["categories", "country", "name", "rate_per_shipment"]);
  });

  it.each([
    ["nombre en blanco", { name: "   " }, "name"],
    ["tarifa 0", { rate: "0" }, "rate_per_shipment"],
    ["email mal formado", { contact_email: "contacto@mrw" }, "contact_email"],
  ])("rechaza %s sin construir payload", (_, change, field) => {
    const { payload, errors } = validateDraft({ ...VALID, ...change });
    expect(payload).toBeNull();
    expect(Object.keys(errors)).toEqual([field]);
  });
});

describe("formatRate", () => {
  it.each([
    [{ rate_per_shipment: 7.45, currency: "EUR" }, "7,45 €"],
    [{ rate_per_shipment: 12.5, currency: "USD" }, "12,50 US$"],
    [{ rate_per_shipment: 0.12345, currency: "EUR" }, "0,1235 €"], // máximo 4 decimales
  ] as const)("formatea %p como %p", (supplier, expected) => {
    expect(plain(formatRate(supplier))).toBe(expected);
  });

  it("con una moneda que Intl no reconoce muestra la tarifa sin formato en lugar de romper la tabla", () => {
    const supplier = { rate_per_shipment: 7.45, currency: "XYZ1" } as unknown as Parameters<typeof formatRate>[0];
    expect(formatRate(supplier)).toBe("7.45 XYZ1");
  });
});

describe("formatDateTime", () => {
  it("formatea una fecha ISO válida en español", () => {
    expect(formatDateTime("2026-10-19T10:05:00Z")).toMatch(/oct 2026/);
  });

  it.each(["", "no-es-una-fecha", "2026-13-45"])("con %p devuelve un texto fijo en lugar de lanzar", (iso) => {
    expect(formatDateTime(iso)).toBe("Fecha no disponible");
  });
});
