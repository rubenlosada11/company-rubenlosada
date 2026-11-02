// Extrae los diagnósticos relevantes de un informe JSON de Lighthouse.
import fs from "node:fs";
const lhr = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const a = lhr.audits;
const show = (id, fn) => {
  const x = a[id];
  if (!x) return;
  console.log(`\n# ${id} score=${x.score} ${x.displayValue ?? ""}`);
  if (fn) fn(x);
};
const items = (x) => x.details?.items ?? [];
console.log(lhr.requestedUrl, lhr.configSettings.formFactor, "LH", lhr.lighthouseVersion);
for (const c of Object.values(lhr.categories)) console.log(c.id, Math.round(c.score * 100));

show("largest-contentful-paint-element", (x) => {
  for (const it of items(x)) console.log(JSON.stringify(it.items ?? it).slice(0, 900));
});
show("lcp-discovery-insight", (x) => console.log(String(JSON.stringify(x.details)).slice(0, 600)));
show("lcp-phases-insight", (x) => console.log(String(JSON.stringify(x.details)).slice(0, 800)));
show("render-blocking-insight", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes, i.wastedMs)));
show("render-blocking-resources", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes, i.wastedMs)));
show("unused-javascript", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes, i.wastedBytes)));
show("unused-css-rules", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes, i.wastedBytes)));
show("bootup-time", (x) => items(x).slice(0, 6).forEach((i) => console.log(i.url, Math.round(i.total), Math.round(i.scripting))));
show("mainthread-work-breakdown", (x) => items(x).forEach((i) => console.log(i.groupLabel, Math.round(i.duration))));
show("long-tasks", (x) => items(x).slice(0, 8).forEach((i) => console.log(i.url, Math.round(i.startTime), Math.round(i.duration))));
show("layout-shifts", (x) => items(x).forEach((i) => console.log(i.score, JSON.stringify(i.node?.snippet ?? i.node?.selector ?? ""), JSON.stringify(i.subItems?.items ?? []).slice(0, 300))));
show("cls-culprits-insight", (x) => console.log(String(JSON.stringify(x.details)).slice(0, 900)));
show("font-display-insight", (x) => items(x).forEach((i) => console.log(i.url, i.wastedMs)));
show("image-delivery-insight", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes, i.wastedBytes)));
show("network-dependency-tree-insight");
show("document-latency-insight", (x) => console.log(String(JSON.stringify(x.details?.items ?? x.details)).slice(0, 500)));
show("server-response-time");
show("total-byte-weight", (x) => items(x).forEach((i) => console.log(i.url, i.totalBytes)));
show("errors-in-console", (x) => items(x).forEach((i) => console.log(i.source, i.description)));
show("third-parties-insight");
for (const cat of ["accessibility", "seo", "best-practices"]) {
  console.log(`\n## fallos ${cat}`);
  for (const ref of lhr.categories[cat].auditRefs) {
    const x = a[ref.id];
    if (ref.weight > 0 && x.score !== null && x.score < 1) {
      console.log(`- ${ref.id} (${x.score}): ${x.title}`);
      for (const i of items(x).slice(0, 8)) console.log("    ", JSON.stringify(i.node?.snippet ?? i.node?.selector ?? i.url ?? i).slice(0, 260), i.node?.explanation ? "| " + i.node.explanation.replace(/\n/g, " ").slice(0, 260) : "");
    }
  }
}
