/**
 * FE-019 — validación del formulario del gestor de incidencias (`lib/incidents.ts`). Ver TESTING.md §10.
 *
 * Mismos límites y mensajes que la API (`packages/analisis-incidencias/.../gestor.py`): título ≤ 120 caracteres,
 * descripción ≤ 2000, y categoría, origen y sede obligatorios.
 */
import {
  DESCRIPTION_MAX_LENGTH,
  EMPTY_INCIDENT_DRAFT,
  TITLE_MAX_LENGTH,
  validateIncidentDraft,
  type IncidentDraft,
} from "@/lib/incidents";

const VALID: IncidentDraft = {
  title: "  Paquete perdido en Zaragoza  ",
  description: " El cliente no ha recibido el envío. ",
  category: "lost_parcel",
  origin: "customer",
  branch: "zaragoza_warehouse",
};

describe("validateIncidentDraft", () => {
  it("con datos válidos devuelve el payload con los textos recortados", () => {
    expect(validateIncidentDraft(VALID)).toEqual({
      errors: {},
      payload: {
        title: "Paquete perdido en Zaragoza",
        description: "El cliente no ha recibido el envío.",
        category: "lost_parcel",
        origin: "customer",
        branch: "zaragoza_warehouse",
      },
    });
  });

  it("acepta título y descripción justo en su longitud máxima (contada tras recortar)", () => {
    const draft = { ...VALID, title: ` ${"t".repeat(TITLE_MAX_LENGTH)} `, description: "d".repeat(DESCRIPTION_MAX_LENGTH) };
    expect(validateIncidentDraft(draft).payload?.title).toHaveLength(TITLE_MAX_LENGTH);
  });

  it.each([
    ["título de 121 caracteres", { title: "t".repeat(TITLE_MAX_LENGTH + 1) }, "title", /120 caracteres/],
    ["descripción de 2001", { description: "d".repeat(DESCRIPTION_MAX_LENGTH + 1) }, "description", /2000/],
    ["título solo con espacios", { title: "    " }, "title", /obligatorio/],
  ])("rechaza %s", (_, change, field, message) => {
    const { payload, errors } = validateIncidentDraft({ ...VALID, ...change });
    expect(payload).toBeNull();
    expect(Object.keys(errors)).toEqual([field]);
    expect(errors[field]).toMatch(message);
  });

  it("con el borrador vacío señala los cinco campos", () => {
    const { payload, errors } = validateIncidentDraft(EMPTY_INCIDENT_DRAFT);
    expect(payload).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["branch", "category", "description", "origin", "title"]);
  });
});
