// Captura PNG de la cabecera (puntuaciones + métricas) de cada informe HTML de Lighthouse de una fase.
// Uso: node shot-reports.mjs <dir de la fase, p. ej. audit/before>
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const phaseDir = process.argv[2];
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const htmls = fs
  .readdirSync(phaseDir, { recursive: true })
  .filter((f) => f.endsWith(".html"))
  .map((f) => path.join(phaseDir, f));

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 }, deviceScaleFactor: 1 });
for (const file of htmls) {
  await page.goto(pathToFileURL(file).href);
  await page.waitForSelector(".lh-scores-header .lh-gauge__percentage");
  // Sin animación de los indicadores, para capturar el valor final.
  await page.addStyleTag({ content: "*{animation:none!important;transition:none!important}" });
  await page.waitForTimeout(800);
  // Desde las cuatro puntuaciones hasta el final del bloque de métricas de rendimiento.
  const top = await page.$eval(".lh-scores-header", (el) => el.getBoundingClientRect().top + window.scrollY);
  const bottom = await page.$eval(
    ".lh-category .lh-metrics-container",
    (el) => el.getBoundingClientRect().bottom + window.scrollY
  );
  const out = file.replace(/\.html$/, ".png");
  await page.screenshot({ path: out, fullPage: true, clip: { x: 0, y: 0, width: 1200, height: bottom + 40 } });
  console.log("png", out);
}
await browser.close();
