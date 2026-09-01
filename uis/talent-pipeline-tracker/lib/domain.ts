import type { CandidateStage, CandidateStatus } from "@/types/api";

/**
 * Etiquetas visibles para People & Talent de TrackFlow. La API expone los
 * valores técnicos (`received`, `personal_interview`, ...); aquí se traducen
 * a la nomenclatura que el equipo usa al hablar de una candidatura.
 */
export const STATUS_LABELS: Record<CandidateStatus, string> = {
  received: "Recibida",
  in_progress: "En proceso",
  selected: "Seleccionada",
  discarded: "Descartada",
};

export const STATUS_ORDER: CandidateStatus[] = ["received", "in_progress", "selected", "discarded"];

export const STAGE_LABELS: Record<CandidateStage, string> = {
  pending: "Pendiente",
  review: "En revisión",
  personal_interview: "Entrevista personal",
  technical_interview: "Entrevista técnica",
  offer_presented: "Oferta presentada",
};

export const STAGE_ORDER: CandidateStage[] = [
  "pending",
  "review",
  "personal_interview",
  "technical_interview",
  "offer_presented",
];

export const STATUS_BADGE_CLASSES: Record<CandidateStatus, string> = {
  received: "bg-slate-100 text-slate-700 border-slate-300",
  in_progress: "bg-blue-100 text-blue-800 border-blue-300",
  selected: "bg-emerald-100 text-emerald-800 border-emerald-300",
  discarded: "bg-rose-100 text-rose-700 border-rose-300",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as CandidateStatus] ?? status;
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage as CandidateStage] ?? stage;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatExperience(years: number): string {
  if (years === 1) return "1 año de experiencia";
  return `${years} años de experiencia`;
}
