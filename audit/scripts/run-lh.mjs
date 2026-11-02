// Medición Lighthouse reproducible de la auditoría de rendimiento.
// Uso: node run-lh.mjs <fase: before|after> <dir audit del repo> <dir de ejecuciones> <token.txt> [runs=5] [filtro]
import fs from "node:fs";
import path from "node:path";
import lighthouse from "lighthouse";
import desktopConfig from "lighthouse/core/config/desktop-config.js";
import * as chromeLauncher from "chrome-launcher";
import puppeteer from "puppeteer-core";
import { computeMedianRun } from "lighthouse/core/lib/median-run.js";

const [phase, auditDir, runsDir, tokenFile, runsArg = "5", filter = ""] = process.argv.slice(2);
const RUNS = Number(runsArg);
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const TOKEN_KEY = "trackflow.backoffice.token";
const token = fs.readFileSync(tokenFile, "utf8").trim();

const targets = [
  { app: "corporate", page: "home", device: "desktop", url: "http://localhost:3001/" },
  { app: "corporate", page: "home", device: "mobile", url: "http://localhost:3001/" },
  { app: "backoffice", page: "dashboard", device: "desktop", url: "http://localhost:3002/", auth: true },
  { app: "backoffice", page: "dashboard", device: "mobile", url: "http://localhost:3002/", auth: true },
  { app: "backoffice", page: "gestor-incidencias", device: "desktop", url: "http://localhost:3002/gestor-incidencias", auth: true },
].filter((t) => !filter || `${t.app}/${t.page}-${t.device}`.includes(filter));

// Prepara el navegador: con sesión, guarda el token en localStorage del origen (sin cargar la app) y vacía la caché.
async function prepare(port, target) {
  const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}` });
  const page = await browser.newPage();
  const client = await page.createCDPSession();
  if (target.auth) {
    await page.goto(new URL("/icon.png", target.url).href);
    await page.evaluate((k, v) => window.localStorage.setItem(k, v), TOKEN_KEY, token);
  }
  await client.send("Network.clearBrowserCache");
  await page.close();
  browser.disconnect();
}

function metrics(lhr) {
  const a = lhr.audits;
  const num = (id) => (a[id] && typeof a[id].numericValue === "number" ? Math.round(a[id].numericValue * 1000) / 1000 : null);
  const score = (id) => Math.round((lhr.categories[id].score ?? 0) * 100);
  return {
    performance: score("performance"),
    accessibility: score("accessibility"),
    bestPractices: score("best-practices"),
    seo: score("seo"),
    fcp: num("first-contentful-paint"),
    lcp: num("largest-contentful-paint"),
    tbt: num("total-blocking-time"),
    cls: num("cumulative-layout-shift"),
    si: num("speed-index"),
    tti: num("interactive"),
    ttfb: num("server-response-time"),
    bytes: num("total-byte-weight"),
    requests: a["network-requests"]?.details?.items?.length ?? null,
    finalUrl: lhr.finalDisplayedUrl,
    lighthouse: lhr.lighthouseVersion,
    userAgent: lhr.environment?.hostUserAgent,
    throttlingMethod: lhr.configSettings.throttlingMethod,
    observedLcp: a.metrics?.details?.items?.[0]?.observedLargestContentfulPaint ?? null,
  };
}

const summary = [];
for (const t of targets) {
  const name = `${t.page}-${t.device}`;
  const runs = [];
  for (let i = 1; i <= RUNS; i++) {
    const chrome = await chromeLauncher.launch({ chromePath: CHROME, chromeFlags: ["--headless=new", "--no-first-run", "--disable-extensions"] });
    try {
      await prepare(chrome.port, t);
      const flags = { port: chrome.port, output: ["json", "html"], logLevel: "error", disableStorageReset: !!t.auth };
      // Comprobación complementaria: LH_THROTTLING=devtools aplica el throttling de verdad en lugar de simularlo.
      if (process.env.LH_THROTTLING) flags.throttlingMethod = process.env.LH_THROTTLING;
      const config = t.device === "desktop" ? desktopConfig : undefined;
      const result = await lighthouse(t.url, flags, config);
      const lhr = result.lhr;
      if (lhr.runtimeError) throw new Error(`${name} run ${i}: ${lhr.runtimeError.code} ${lhr.runtimeError.message}`);
      if (t.auth && new URL(lhr.finalDisplayedUrl).pathname.startsWith("/login")) throw new Error(`${name}: redirigido a /login (sin sesión)`);
      const base = path.join(runsDir, phase, t.app, `${name}-run${i}`);
      fs.mkdirSync(path.dirname(base), { recursive: true });
      fs.writeFileSync(`${base}.json`, result.report[0]);
      fs.writeFileSync(`${base}.html`, result.report[1]);
      const m = metrics(lhr);
      runs.push({ run: i, lhr, base, ...m });
      console.log(`${t.app}/${name} run ${i}: P${m.performance} A${m.accessibility} BP${m.bestPractices} SEO${m.seo} LCP ${Math.round(m.lcp)} TBT ${Math.round(m.tbt)} CLS ${m.cls} FCP ${Math.round(m.fcp)} -> ${m.finalUrl}`);
    } finally {
      await chrome.kill();
    }
  }
  // Mediana con el algoritmo de Lighthouse (ejecución más cercana a la mediana de FCP e Interactive).
  const median = computeMedianRun(runs.map((r) => r.lhr));
  const medianRun = runs.find((r) => r.lhr === median);
  const outBase = path.join(auditDir, phase, t.app, name);
  fs.mkdirSync(path.dirname(outBase), { recursive: true });
  fs.copyFileSync(`${medianRun.base}.json`, `${outBase}.json`);
  fs.copyFileSync(`${medianRun.base}.html`, `${outBase}.html`);
  const strip = ({ lhr, base, ...rest }) => rest;
  summary.push({ app: t.app, page: t.page, device: t.device, url: t.url, medianRun: medianRun.run, median: strip(medianRun), runs: runs.map(strip) });
  console.log(`  mediana: run ${medianRun.run}`);
}

const summaryFile = path.join(auditDir, phase, "runs.json");
const previous = fs.existsSync(summaryFile) ? JSON.parse(fs.readFileSync(summaryFile, "utf8")) : [];
const merged = [...previous.filter((p) => !summary.some((s) => s.app === p.app && s.page === p.page && s.device === p.device)), ...summary];
fs.writeFileSync(summaryFile, JSON.stringify(merged, null, 2) + "\n");
console.log("resumen:", summaryFile);
