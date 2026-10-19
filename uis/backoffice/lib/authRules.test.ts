/**
 * AUTH-088 — reglas de contraseña del backoffice (`lib/authRules.ts`), iguales que las de `services/api`.
 * Ver TESTING.md §9.
 */
import { EMAIL_PATTERN, passwordProblem } from "@/lib/authRules";

describe("passwordProblem", () => {
  it.each([
    ["8 caracteres", "a".repeat(8)],
    ["72 bytes con ñ (36 × 2 bytes)", "ñ".repeat(36)],
    ["espacios en los extremos (se guardan tal cual)", "  frase de paso  "],
  ])("acepta %s", (_, password) => {
    expect(passwordProblem(password)).toBeNull();
  });

  it("rechaza 7 caracteres por longitud", () => {
    expect(passwordProblem("a".repeat(7))).toMatch(/al menos 8 caracteres/);
  });

  it("rechaza 73 bytes aunque tenga solo 37 caracteres", () => {
    const password = "ñ".repeat(36) + "a";
    expect(password).toHaveLength(37);
    expect(passwordProblem(password)).toMatch(/72 bytes/);
  });
});

describe("EMAIL_PATTERN", () => {
  it.each(["ana@trackflow.test", "laura.gomez@almacen.trackflow.test"])("acepta %s", (email) => {
    expect(EMAIL_PATTERN.test(email)).toBe(true);
  });

  it.each(["ana@trackflow", "ana trackflow.test", "@trackflow.test", "ana@@trackflow.test"])("rechaza %s", (email) => {
    expect(EMAIL_PATTERN.test(email)).toBe(false);
  });
});
