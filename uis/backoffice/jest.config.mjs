import nextJest from "next/jest.js";

// `next/jest` compila TypeScript con SWC (como `next build`), resuelve el alias `@/` del tsconfig y carga `.env*`.
const createJestConfig = nextJest({ dir: "./" });

/** Tests unitarios de las utilidades de `lib/` (ver TESTING.md en la raíz del repo). */
const config = {
  // Sin jsdom: las utilidades no dependen del DOM; los tests de `lib/session.ts` simulan `window.localStorage`.
  testEnvironment: "node",
  testMatch: ["<rootDir>/lib/**/*.test.ts"],
  collectCoverageFrom: ["lib/**/*.ts", "!lib/data/**"],
};

export default createJestConfig(config);
