/**
 * `lib/telemetryCatalog.ts` frente al catálogo aprobado (`docs/telemetry/event-schemas.json`): mismos eventos del
 * frontend, mismas propiedades, misma versión, mismas reglas de `sessionId`/`requestId` y mismos enums.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ALLOWLIST, FORM_FIELDS, FORM_IDS, SECTIONS } from "@/lib/telemetryCatalog";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const schema: Json = JSON.parse(
  readFileSync(join(__dirname, "..", "..", "..", "docs", "telemetry", "event-schemas.json"), "utf8")
);

function eventPart(eventType: string): Json {
  return schema.definitions[eventType].allOf[1].properties;
}

const frontendEvents = (schema["x-eventTypes"] as string[]).filter((name) =>
  (schema.definitions[name]["x-sources"] as string[]).includes("frontend")
);

it("contiene exactamente los eventos del catálogo con fuente frontend", () => {
  expect(Object.keys(ALLOWLIST).sort()).toEqual([...frontendEvents].sort());
});

describe.each(frontendEvents)("%s", (eventType) => {
  const part = eventPart(eventType);
  const spec = ALLOWLIST[eventType as keyof typeof ALLOWLIST];

  it("misma versión de esquema", () => {
    expect(spec.schemaVersion).toBe(part.schemaVersion.const);
  });

  it("misma allowlist (todas obligatorias)", () => {
    expect([...spec.properties].sort()).toEqual(Object.keys(part.properties.properties).sort());
    expect([...spec.properties].sort()).toEqual([...part.properties.required].sort());
    expect(part.properties.additionalProperties).toBe(false);
  });

  it("mismas reglas de sessionId y requestId", () => {
    const sessionNullable = JSON.stringify(part.sessionId).includes('"null"');
    expect(spec.requiresSession).toBe(!sessionNullable);
    const requestAlwaysNull = part.requestId.type === "null";
    expect(spec.hasRequestId).toBe(!requestAlwaysNull);
  });

  it("userId siempre admite nulo (lo pone el receptor)", () => {
    expect(JSON.stringify(part.userId)).toContain('"null"');
  });
});

it("mismas secciones, formularios y campos", () => {
  expect([...SECTIONS]).toEqual(schema.definitions.section.enum);
  expect([...FORM_IDS]).toEqual(schema.definitions.form_id.enum);
  expect([...FORM_FIELDS]).toEqual(schema.definitions.form_field.enum);
});
