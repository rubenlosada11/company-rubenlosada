#!/usr/bin/env node
// Comprueba que una ruta HTTP responde 200 con HTML y con el contenido esperado.
//
// Uso:
//   node check-route.mjs <url> [--expect "texto"]... [--forbid "texto"]... [--timeout 60]
//
// - Reintenta cada segundo hasta `--timeout` (por defecto 60 s): sirve para esperar a que arranque el servidor.
// - --expect: subcadena que DEBE aparecer en el HTML (repetible).
// - --forbid: subcadena que NO debe aparecer (repetible). Se añaden por defecto las páginas de error de Next.js.
// Código de salida: 0 = OK, 1 = fallo, 2 = uso incorrecto.

const DEFAULT_FORBIDDEN = [
  "Application error",
  "Internal Server Error",
  "This page could not be found",
  "Unhandled Runtime Error",
];

const args = process.argv.slice(2);
const url = args.shift();
const expected = [];
const forbidden = [...DEFAULT_FORBIDDEN];
let timeoutSeconds = 60;

while (args.length > 0) {
  const flag = args.shift();
  const value = args.shift();
  if (value === undefined) usage(`Falta el valor de ${flag}`);
  if (flag === "--expect") expected.push(value);
  else if (flag === "--forbid") forbidden.push(value);
  else if (flag === "--timeout") timeoutSeconds = Number(value);
  else usage(`Argumento desconocido: ${flag}`);
}

if (!url || !/^https?:\/\//.test(url) || !Number.isFinite(timeoutSeconds)) {
  usage("Uso: node check-route.mjs <url> [--expect texto]... [--forbid texto]... [--timeout segundos]");
}

function usage(message) {
  console.error(message);
  process.exit(2);
}

async function attempt() {
  const res = await fetch(url, { redirect: "manual" });
  const body = await res.text();
  const type = res.headers.get("content-type") ?? "";
  const problems = [];

  if (res.status !== 200) problems.push(`estado HTTP ${res.status} (se esperaba 200)`);
  if (!type.includes("text/html")) problems.push(`content-type "${type}" (se esperaba text/html)`);
  for (const text of expected) {
    if (!body.includes(text)) problems.push(`no aparece el texto esperado: "${text}"`);
  }
  for (const text of forbidden) {
    if (body.includes(text)) problems.push(`aparece un texto prohibido: "${text}"`);
  }

  return { problems, summary: `${res.status} (${type || "sin content-type"}, ${body.length} bytes)` };
}

const deadline = Date.now() + timeoutSeconds * 1000;
let last = "sin respuesta";

while (true) {
  try {
    const { problems, summary } = await attempt();
    if (problems.length === 0) {
      console.log(`OK   ${url} -> ${summary}; esperados encontrados: ${expected.length}/${expected.length}`);
      process.exit(0);
    }
    last = `${summary}: ${problems.join("; ")}`;
  } catch (error) {
    last = `error de red: ${error instanceof Error ? error.message : String(error)}`;
  }

  if (Date.now() >= deadline) {
    console.error(`FAIL ${url} -> ${last}`);
    process.exit(1);
  }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}
