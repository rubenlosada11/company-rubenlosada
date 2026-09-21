import type { BaselineFact } from "@/types";

/**
 * Datos de partida documentados en CONTEXT.es.md. Son cifras del briefing (aproximadas), NO métricas en vivo:
 * no existe todavía conexión con ningún sistema real.
 */
export const BASELINE_FACTS: readonly BaselineFact[] = [
  { label: "Empleados", value: "~130", detail: "Entre Estados Unidos y España." },
  { label: "Almacenes", value: "2", detail: "Los Ángeles y Zaragoza, con sistemas distintos." },
  { label: "Transportistas", value: "8", detail: "En los dos países, incluidos dos locales." },
  { label: "Devoluciones", value: "18–25 %", detail: "Del volumen total según cliente y país." },
  { label: "Consultas automatizables", value: "~80 %", detail: "De las que atienden hoy los agentes de CX." },
  { label: "Facturación anual", value: "~9 M€", detail: "Aproximada." },
];
