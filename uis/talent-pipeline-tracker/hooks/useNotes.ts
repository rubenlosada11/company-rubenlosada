import { useEffect, useState } from "react";
import { ApiError } from "@/lib/http";
import { recordsService } from "@/services/records";
import type { Note } from "@/types/api";

type NotesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: Note[] };

const FALLBACK_MESSAGE = "No se pudieron cargar las notas. Inténtalo de nuevo.";

/** No expone `reload`: el componente que lo usa debe remontar con un `key`
 * distinto para forzar una nueva carga (ver nota en useCandidates.ts). */
export function useNotes(recordId: string) {
  const [state, setState] = useState<NotesState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    recordsService
      .listNotes(recordId)
      .then((res) => {
        if (!cancelled) setState({ status: "success", data: res.data });
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
  }, [recordId]);

  function addNoteLocally(note: Note) {
    setState((prev) => (prev.status === "success" ? { status: "success", data: [note, ...prev.data] } : prev));
  }

  function removeNoteLocally(noteId: string) {
    setState((prev) =>
      prev.status === "success"
        ? { status: "success", data: prev.data.filter((n) => n.id !== noteId) }
        : prev
    );
  }

  return { state, addNoteLocally, removeNoteLocally };
}
