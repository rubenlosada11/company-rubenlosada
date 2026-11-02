// Tablas Markdown con la mediana por métrica (5 ejecuciones) de una fase, o la comparativa before/after.
// Uso: node summarize.mjs <audit dir> [before|after|compare]
import fs from "node:fs";
import path from "node:path";

const [auditDir, mode = "before"] = process.argv.slice(2);
const load = (phase) => JSON.parse(fs.readFileSync(path.join(auditDir, phase, "runs.json"), "utf8"));
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const KEYS = ["performance", "accessibility", "bestPractices", "seo", "fcp", "lcp", "tbt", "cls", "si", "ttfb", "bytes", "requests"];
const med = (entry) => Object.fromEntries(KEYS.map((k) => [k, median(entry.runs.map((r) => r[k] ?? 0))]));
const fmt = (k, v) => {
  if (["fcp", "lcp", "tbt", "si", "ttfb"].includes(k)) return `${Math.round(v)} ms`;
  if (k === "cls") return v.toFixed(3);
  if (k === "bytes") return `${Math.round(v / 1024)} KiB`;
  return String(Math.round(v));
};
const label = (e) => `${e.app} · ${e.page} · ${e.device}`;

if (mode === "compare") {
  const before = load("before");
  const after = load("after");
  console.log("| Aplicación | Página | Dispositivo | Métrica | Antes | Después | Diferencia |\n|---|---|---|---|---|---|---|");
  for (const b of before) {
    const a = after.find((x) => x.app === b.app && x.page === b.page && x.device === b.device);
    if (!a) continue;
    const mb = med(b);
    const ma = med(a);
    for (const k of KEYS) {
      const d = ma[k] - mb[k];
      const sign = d > 0 ? "+" : "";
      const diff = k === "cls" ? `${sign}${d.toFixed(3)}` : ["fcp", "lcp", "tbt", "si", "ttfb"].includes(k) ? `${sign}${Math.round(d)} ms` : k === "bytes" ? `${sign}${Math.round(d / 1024)} KiB` : `${sign}${Math.round(d)}`;
      console.log(`| ${b.app} | ${b.page} | ${b.device} | ${k} | ${fmt(k, mb[k])} | ${fmt(k, ma[k])} | ${diff} |`);
    }
  }
} else {
  const data = load(mode);
  console.log("| Página | Perf. | Acc. | BP | SEO | FCP | LCP | TBT | CLS | SI | TTFB | Peso | Peticiones | Ejecución mediana |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|");
  for (const e of data) {
    const m = med(e);
    console.log(`| ${label(e)} | ${KEYS.map((k) => fmt(k, m[k])).join(" | ")} | run ${e.medianRun} |`);
  }
  console.log("\nEjecuciones individuales (Perf. / LCP / TBT / CLS):");
  for (const e of data) console.log(`- ${label(e)}: ${e.runs.map((r) => `${r.performance}/${Math.round(r.lcp)}/${Math.round(r.tbt)}/${r.cls.toFixed(3)}`).join(" · ")}`);
}
