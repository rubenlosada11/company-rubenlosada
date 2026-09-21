#!/usr/bin/env node
// Detecta cambios accidentales en el árbol de trabajo de Git antes de un commit.
//
// Uso (desde cualquier carpeta del repo):
//   node .agents/skills/validate-delivery/scripts/check-hygiene.mjs [--allow <prefijo>]...
//
// - Falla si hay ficheros generados o sensibles sin ignorar (node_modules, .next, *.tsbuildinfo, next-env.d.ts,
//   .env* salvo .env.example, logs, AGENTS.md/CLAUDE.md dentro de una app de uis/).
// - Con --allow, falla si algún cambio queda FUERA de los prefijos indicados (p. ej. --allow uis/website).
// - Falla si la rama actual es main.
// Código de salida: 0 = limpio, 1 = hay problemas.

import { execFileSync } from "node:child_process";

const allow = [];
const argv = process.argv.slice(2);
while (argv.length > 0) {
  const flag = argv.shift();
  const value = argv.shift();
  if (flag !== "--allow" || !value) {
    console.error("Uso: node check-hygiene.mjs [--allow <prefijo>]...");
    process.exit(1);
  }
  allow.push(value.replace(/\\/g, "/").replace(/\/+$/, ""));
}

const git = (...gitArgs) => execFileSync("git", gitArgs, { encoding: "utf8" });

const branch = git("branch", "--show-current").trim();
const lines = git("status", "--porcelain", "-uall").split("\n").filter(Boolean);

const paths = lines.map((line) => {
  const raw = line.slice(3);
  const target = raw.includes(" -> ") ? raw.split(" -> ").pop() : raw;
  return target.replace(/^"|"$/g, "");
});

const forbidden = [
  [/(^|\/)node_modules\//, "dependencias instaladas"],
  [/(^|\/)\.next\//, "salida de build de Next.js"],
  [/\.tsbuildinfo$/, "caché de TypeScript"],
  [/(^|\/)next-env\.d\.ts$/, "fichero generado por Next.js"],
  [/(^|\/)\.env(\.(?!example$)[^/]+)?$/, "fichero de entorno / posibles secretos"],
  [/\.(log|pem)$/, "log o clave"],
  [/(^|\/)\.DS_Store$/, "basura del sistema"],
  [/^uis\/[^/]+\/(AGENTS|CLAUDE)\.md$/, "fichero de hints regenerado por Next.js dentro de una app"],
];

const problems = [];
if (branch === "main") problems.push("La rama actual es main: trabaja en una rama feature/*.");

for (const path of paths) {
  for (const [pattern, reason] of forbidden) {
    if (pattern.test(path)) problems.push(`Accidental (${reason}): ${path}`);
  }
  if (allow.length > 0 && !allow.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) {
    problems.push(`Fuera de alcance (${allow.join(", ")}): ${path}`);
  }
}

console.log(`Rama: ${branch || "(detached)"} · ficheros cambiados/sin seguimiento: ${paths.length}`);
if (problems.length === 0) {
  console.log("OK   sin cambios accidentales ni fuera de alcance.");
  process.exit(0);
}
for (const problem of problems) console.error(`FAIL ${problem}`);
process.exit(1);
