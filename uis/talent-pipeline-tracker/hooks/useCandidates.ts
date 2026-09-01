import { useEffect, useState } from "react";
import { ApiError } from "@/lib/http";
import { recordsService } from "@/services/records";
import type { CandidateListItem, CandidateStage, CandidateStatus } from "@/types/api";

type ListState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: CandidateListItem[]; total: number };

const FALLBACK_MESSAGE = "No se pudieron cargar las candidaturas. Inténtalo de nuevo.";

/**
 * Nota: no expone `reload`. El estado inicial de "loading" viene del `useState`
 * inicial; para forzar una nueva carga (cambio de filtros o reintento tras un
 * error) el componente que consume este hook debe remontarlo con un `key`
 * distinto en vez de resetear el estado dentro del efecto (evita renders en
 * cascada, ver regla `react-hooks/set-state-in-effect`).
 */
export function useCandidates(filters: { status?: CandidateStatus; stage?: CandidateStage }) {
  const [state, setState] = useState<ListState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    recordsService
      .list({ status: filters.status, stage: filters.stage })
      .then((res) => {
        if (cancelled) return;
        setState({ status: "success", data: res.data, total: res.total });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          status: "error",
          message: err instanceof ApiError ? err.message : FALLBACK_MESSAGE,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [filters.status, filters.stage]);

  return state;
}
