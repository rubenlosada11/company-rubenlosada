/**
 * AUTH-088 — nombre e iniciales del usuario conectado (`lib/auth.ts`). Ver TESTING.md §9.
 */
import { displayName, initials } from "@/lib/auth";
import type { CurrentUser } from "@/types/auth";

function user(email: string, name: string | null = null): CurrentUser {
  return {
    id: "id-de-prueba",
    email,
    role: "user",
    is_active: true,
    created_at: "2026-10-19T10:00:00Z",
    profile: { id: "perfil", user_id: "id-de-prueba", name, phone: null, address: null },
  };
}

describe("displayName", () => {
  it("usa el nombre del perfil", () => {
    expect(displayName(user("laura@trackflow.test", "Laura Gómez"))).toBe("Laura Gómez");
  });

  it.each([null, "", "   "])("sin nombre útil (%p) usa la parte local del email", (name) => {
    expect(displayName(user("laura.gomez@trackflow.test", name))).toBe("laura.gomez");
  });
});

describe("initials", () => {
  it.each([
    ["nombre y apellido", user("x@trackflow.test", "Laura Gómez"), "LG"],
    ["email con punto", user("laura.gomez@trackflow.test"), "LG"],
    ["email con guion bajo", user("ana_ruiz@trackflow.test"), "AR"],
    ["una sola palabra", user("laura@trackflow.test"), "LA"],
    ["nombre con tilde inicial", user("x@trackflow.test", "Ángela ñúñez"), "ÁÑ"],
  ])("%s", (_, who, expected) => {
    expect(initials(who)).toBe(expected);
  });
});
