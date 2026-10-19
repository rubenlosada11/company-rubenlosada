/**
 * AUTH-088 — utilidades de sesión del backoffice (`lib/session.ts`). Ver TESTING.md §9.
 *
 * Entorno `node` (sin jsdom): `window` no existe salvo en los tests que lo simulan, y solo se simula su
 * `localStorage` (la frontera con el navegador). Las funciones que se prueban son las reales.
 */
import { clearToken, readToken, safeNextPath, saveToken, TOKEN_KEY, tokenExpiry } from "@/lib/session";

function base64url(data: object): string {
  return Buffer.from(JSON.stringify(data)).toString("base64url");
}

function jwt(payload: object): string {
  return `${base64url({ alg: "HS256", typ: "JWT" })}.${base64url(payload)}.firma`;
}

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, value),
  };
}

function blockedStorage(): Storage {
  const blocked = () => {
    throw new Error("SecurityError: el almacenamiento está bloqueado");
  };
  return { length: 0, clear: blocked, getItem: blocked, key: blocked, removeItem: blocked, setItem: blocked };
}

function withWindow(localStorage: Storage): void {
  Object.defineProperty(globalThis, "window", { value: { localStorage }, configurable: true, writable: true });
}

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe("tokenExpiry", () => {
  it("devuelve el exp del JWT en milisegundos", () => {
    expect(tokenExpiry(jwt({ sub: "id", exp: 1_760_868_000 }))).toBe(1_760_868_000_000);
  });

  it("lee un payload base64url con - y _ y sin relleno", () => {
    const token = jwt({ exp: 1_760_868_000, d: "~~~???>>>" });
    const payload = token.split(".")[1];
    expect(payload).toMatch(/[-_]/); // premisa del caso
    expect(payload.length % 4).not.toBe(0);
    expect(tokenExpiry(token)).toBe(1_760_868_000_000);
  });

  it.each([
    ["sin segunda parte", "solo-una-parte"],
    ["payload que no es JSON", `${base64url({ alg: "HS256" })}.${Buffer.from("no es json").toString("base64url")}.x`],
    ["exp en texto", jwt({ exp: "1760868000" })],
    ["sin exp", jwt({ sub: "id" })],
    ["vacío", ""],
  ])("devuelve null con un token %s", (_, token) => {
    expect(tokenExpiry(token)).toBeNull();
  });
});

describe("safeNextPath", () => {
  it.each(["/", "/suppliers?country=ES", "/account/profile#datos", "/loginx", "/login-history"])(
    "permite la ruta interna %s",
    (path) => {
      expect(safeNextPath(path)).toBe(path);
    },
  );

  it.each([
    ["nula", null],
    ["vacía", ""],
    ["absoluta a otro dominio", "https://evil.example/"],
    ["protocolo relativo", "//evil.example"],
    ["con barra invertida", "/\\evil.example"],
    ["relativa sin barra", "suppliers"],
    ["login", "/login"],
    ["login con parámetros", "/login?next=/"],
    ["login con barra final", "/login/"],
    ["registro", "/register"],
    ["recuperación con token", "/reset-password?token=abc"],
    ["olvido de contraseña", "/forgot-password"],
  ])("devuelve / para una ruta %s", (_, value) => {
    expect(safeNextPath(value)).toBe("/");
  });
});

describe("readToken / saveToken / clearToken", () => {
  it("guarda, lee y borra el token con su clave", () => {
    const storage = memoryStorage();
    withWindow(storage);

    expect(saveToken("token-de-prueba")).toBe(true);
    expect(storage.getItem(TOKEN_KEY)).toBe("token-de-prueba");
    expect(readToken()).toBe("token-de-prueba");

    clearToken();
    expect(readToken()).toBeNull();
  });

  it("sin window (render en el servidor) no hay token ni se puede guardar", () => {
    expect(readToken()).toBeNull();
    expect(saveToken("token-de-prueba")).toBe(false);
    expect(() => clearToken()).not.toThrow();
  });

  it("con el almacenamiento bloqueado no hay sesión, pero nada lanza", () => {
    withWindow(blockedStorage());
    expect(saveToken("token-de-prueba")).toBe(false);
    expect(readToken()).toBeNull();
    expect(() => clearToken()).not.toThrow();
  });
});
