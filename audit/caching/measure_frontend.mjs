// Medición en navegador de la carga diferida y del `useMemo` del backoffice (`CACHING_REPORT.md`).
//
// Con el build de producción del backoffice (`next build` + `next start`) y la API arrancada sobre el dataset de
// benchmark, abre Microsoft Edge sin interfaz con `playwright-core` (instalado fuera del repo) y mide:
//
// 1. /proveedores: JavaScript descargado al cargar la página y al pulsar «Nuevo proveedor», y tiempo desde el clic
//    hasta ver el formulario en dos casos: clic inmediato (peor caso: la precarga al pasar el puntero no ha
//    terminado) y clic tras 150 ms con el puntero sobre el botón (lo habitual al apuntar con el ratón).
// 2. /incidencias: JavaScript descargado al cargar la página y al analizar un CSV (resultados).
// 3. /inventory/orders/outbound: tiempo de cada pulsación en «Cantidad» con el selector de 1.000 productos,
//    con la CPU ralentizada ×4 (CDP): una ronda de calentamiento que no cuenta y 7 rondas de 60 pulsaciones
//    (mediana de cada ronda y mediana de las rondas).
//
// También anota los errores de consola y de página (p. ej. de hidratación) de todo el recorrido.
//
// El sidebar hace *prefetch* de las rutas enlazadas y eso descargaría el JavaScript de otras páginas: las peticiones
// de prefetch (`next-router-prefetch`) se bloquean para medir solo lo que necesita cada ruta.
//
// Uso (desde la raíz del repo):
//   node audit/caching/measure_frontend.mjs --playwright <carpeta con node_modules/playwright-core> \
//     --email benchmark@trackflow.test --password <contraseña> --out audit/caching/results/frontend-before.json

import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, value, index, all) => {
    if (value.startsWith("--")) pairs.push([value.slice(2), all[index + 1]]);
    return pairs;
  }, [])
);
const BASE = args.base ?? "http://localhost:3002";
const API = args.api ?? "http://localhost:8031";
const EDGE = args.edge ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const CSV = resolve(args.csv ?? "scripts/incidents-trackflow.csv");
const ROUNDS = Number(args.rounds ?? 7);
const KEYSTROKES = Number(args.keystrokes ?? 60);

const require = createRequire(join(resolve(args.playwright), "package.json"));
const { chromium } = require("playwright-core");

async function token() {
  const response = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: args.email, password: args.password }),
  });
  if (!response.ok) throw new Error(`Login fallido: ${response.status}`);
  return (await response.json()).access_token;
}

/** Recoge las respuestas JavaScript (ruta y bytes transferidos) desde que se llama hasta `stop()`. */
function collectScripts(page) {
  const scripts = [];
  const onFinished = async (request) => {
    if (request.resourceType() !== "script") return;
    const sizes = await request.sizes().catch(() => null);
    scripts.push({ path: new URL(request.url()).pathname, bytes: sizes?.responseBodySize ?? 0 });
  };
  page.on("requestfinished", onFinished);
  return {
    stop: async () => {
      await page.waitForTimeout(300);
      page.off("requestfinished", onFinished);
      return { count: scripts.length, bytes: scripts.reduce((sum, s) => sum + s.bytes, 0), files: scripts };
    },
  };
}

async function freshPage(browser, jwt, errors) {
  const context = await browser.newContext({ viewport: { width: 1350, height: 940 } });
  await context.route("**/*", (route) => {
    const headers = route.request().headers();
    if (headers["next-router-prefetch"] || headers["next-router-segment-prefetch"]) return route.abort();
    return route.continue();
  });
  const page = await context.newPage();
  // `/icon.png` no carga la app: solo sirve para escribir el token en el `localStorage` del origen.
  await page.goto(`${BASE}/icon.png`);
  await page.evaluate((value) => localStorage.setItem("trackflow.backoffice.token", value), jwt);
  page.on("console", (message) => {
    const prefetch = message.text().includes("ERR_FAILED");
    if (message.type() === "error" && !prefetch) errors.push(`${page.url()} console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`${page.url()} pageerror: ${error.message}`));
  return { page, context };
}

async function suppliers(browser, jwt, errors) {
  const { page, context } = await freshPage(browser, jwt, errors);
  const initial = collectScripts(page);
  await page.goto(`${BASE}/proveedores`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Nuevo proveedor" }).waitFor();
  const load = await initial.stop();

  const onDemand = collectScripts(page);
  const started = Date.now();
  await page.getByRole("button", { name: "Nuevo proveedor" }).click();
  await page.locator("#new-supplier-panel form").waitFor();
  const formMs = Date.now() - started;
  const click = await onDemand.stop();
  await context.close();

  const second = await freshPage(browser, jwt, errors);
  await second.page.goto(`${BASE}/proveedores`, { waitUntil: "networkidle" });
  const button = second.page.getByRole("button", { name: "Nuevo proveedor" });
  await button.hover();
  await second.page.waitForTimeout(150);
  const afterHover = Date.now();
  await button.click();
  await second.page.locator("#new-supplier-panel form").waitFor();
  const formAfterHoverMs = Date.now() - afterHover;
  await second.context.close();
  return {
    route: "/proveedores",
    initial: load,
    onDemand: { ...click, msUntilFormVisible: formMs, msUntilFormVisibleAfterHover: formAfterHoverMs },
  };
}

async function incidents(browser, jwt, errors) {
  const { page, context } = await freshPage(browser, jwt, errors);
  const initial = collectScripts(page);
  await page.goto(`${BASE}/incidencias`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Analizar CSV" }).waitFor();
  const load = await initial.stop();

  const onDemand = collectScripts(page);
  await page.locator('input[type="file"]').setInputFiles(CSV);
  const started = Date.now();
  await page.getByRole("button", { name: "Analizar CSV" }).click();
  await page.getByRole("heading", { name: "Resumen general" }).waitFor();
  const resultsMs = Date.now() - started;
  const analyse = await onDemand.stop();
  await context.close();
  return { route: "/incidencias", initial: load, onDemand: { ...analyse, msUntilResultsVisible: resultsMs } };
}

/** Mediana de lo que tarda React en procesar y confirmar cada pulsación en «Cantidad» (CPU ×4). */
async function outboundTyping(browser, jwt, errors) {
  const { page, context } = await freshPage(browser, jwt, errors);
  await page.goto(`${BASE}/inventory/orders/outbound`, { waitUntil: "networkidle" });
  const options = await page.locator("#outbound-sku_id option").count();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

  const rounds = [];
  for (let round = 0; round <= ROUNDS; round += 1) {
    const samples = await page.evaluate(async (count) => {
      const input = document.getElementById("outbound-quantity");
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      const nextTask = () =>
        new Promise((done) => {
          const channel = new MessageChannel();
          channel.port1.onmessage = () => done();
          channel.port2.postMessage(null);
        });
      const times = [];
      for (let i = 0; i < count; i += 1) {
        const value = String((i % 9) + 1).repeat((i % 3) + 1);
        const start = performance.now();
        setValue.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        await nextTask(); // React confirma la actualización de un evento discreto antes de la siguiente tarea
        times.push(performance.now() - start);
      }
      return times;
    }, KEYSTROKES);
    samples.sort((a, b) => a - b);
    if (round === 0) continue; // calentamiento (JIT, cachés del navegador)
    rounds.push(Number(samples[Math.floor(samples.length / 2)].toFixed(3)));
  }
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  await context.close();
  const sorted = [...rounds].sort((a, b) => a - b);
  return {
    route: "/inventory/orders/outbound",
    productOptions: options,
    cpuThrottling: 4,
    keystrokesPerRound: KEYSTROKES,
    roundMedianMs: rounds,
    medianMs: sorted[Math.floor(sorted.length / 2)],
  };
}

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const jwt = await token();
const errors = [];
try {
  const report = {
    label: args.label ?? "",
    date: new Date().toISOString(),
    browser: `Microsoft Edge ${browser.version()}`,
    suppliers: await suppliers(browser, jwt, errors),
    incidents: await incidents(browser, jwt, errors),
    outboundTyping: await outboundTyping(browser, jwt, errors),
    errors,
  };
  mkdirSync(dirname(resolve(args.out)), { recursive: true });
  writeFileSync(resolve(args.out), `${JSON.stringify(report, null, 2)}\n`);
  for (const key of ["suppliers", "incidents"]) {
    const r = report[key];
    console.log(
      `${r.route}: inicial ${r.initial.count} JS / ${r.initial.bytes} B · bajo demanda ${r.onDemand.count} JS / ${r.onDemand.bytes} B`
    );
  }
  console.log(
    `${report.outboundTyping.route}: ${report.outboundTyping.productOptions} opciones · pulsación mediana ${report.outboundTyping.medianMs} ms (rondas ${report.outboundTyping.roundMedianMs.join(", ")})`
  );
  console.log(`Errores de consola/página: ${errors.length}`);
  for (const error of errors) console.log(`  ${error}`);
} finally {
  await browser.close();
}
