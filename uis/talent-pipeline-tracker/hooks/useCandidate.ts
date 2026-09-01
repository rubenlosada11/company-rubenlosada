import { useEffect, useState } from "react";
import { ApiError } from "@/lib/http";
import { recordsService } from "@/services/records";
import type { Candidate } from "@/types/api";

type CandidateState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: Candidate };

const FALLBACK_MESSAGE = "No se pudo cargar la candidatura. Inténtalo de nuevo.";

/** No expone `reload`: el componente que lo usa debe remontar con un `key`
 * distinto para forzar una nueva carga (ver nota en useCandidates.ts). */
export function useCandidate(id: string) {
  const [state, setState] = useState<CandidateState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    recordsService
      .getById(id)
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: err instanceof ApiError ? err.message : FALLBACK_MESSAGE,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  function setCandidate(data: Candidate) {
    setState({ status: "success", data });
  }

  return { state, setCandidate };
}
