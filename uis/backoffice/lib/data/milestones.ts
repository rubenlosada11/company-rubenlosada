import type { Milestone } from "@/types";

/** Fuente: docs/hitos.md. Un hito se marca “entregado” cuando su Pull Request se fusiona en `main`. */
export const MILESTONES: readonly Milestone[] = [
  {
    number: 1,
    name: "Sitio web público",
    status: "delivered",
    summary: "Landing comercial y formulario de captación de leads con validación completa.",
    paths: ["uis/landing/"],
    demos: [{ label: "Demo pública", url: "https://landingtrackflow.rubenlosada.com/" }],
  },
  {
    number: 2,
    name: "Scripts de automatización y procesamiento de datos",
    status: "delivered",
    summary:
      "Modelos de dominio y utilidades TypeScript (filtrado, ordenamiento, búsqueda, agregaciones y validaciones) con interfaz de prueba manual.",
    paths: ["packages/shared/", "uis/script-automatizacion/"],
    demos: [{ label: "Demo pública", url: "https://scriptsautotrackflow.rubenlosada.com/" }],
  },
  {
    number: 3,
    name: "Talent Pipeline Tracker",
    status: "delivered",
    summary:
      "Aplicación Next.js de People & Talent para gestionar el pipeline de candidaturas sobre la API pública de Talent Tracker.",
    paths: ["uis/talent-pipeline-tracker/"],
    demos: [{ label: "Demo pública", url: "https://talent-pipeline-tracker.rubenlosada.com/" }],
  },
  {
    number: 4,
    name: "Ingeniería impulsada por IA",
    status: "delivered", // PR #3 fusionada en main el 2026-09-21
    summary:
      "Memory bank, AGENTS.md, reglas y skill para agentes; web corporativa y backoffice sobre el contexto de empresa.",
    paths: ["memory-bank/", "AGENTS.md", ".agents/", "uis/website/", "uis/backoffice/"],
    demos: [
      { label: "Demo website", url: "https://websitetrackflow.rubenlosada.com/" },
      { label: "Demo backoffice", url: "https://backofficetrackflow.rubenlosada.com/" },
    ],
  },
];
