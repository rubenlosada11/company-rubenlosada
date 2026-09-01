import { http } from "@/lib/http";
import type {
  Candidate,
  CandidateCreatePayload,
  CandidatePatchPayload,
  Note,
  NoteCreatePayload,
  NotesListResponse,
  RecordsListResponse,
  RecordsQuery,
} from "@/types/api";

/** Sin límite máximo documentado por la API: se pide un lote amplio para poder
 * filtrar/buscar en cliente sin lanzar peticiones adicionales por cada tecleo. */
const DEFAULT_LIST_LIMIT = 200;

function buildQuery(query: RecordsQuery): string {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.stage) params.set("stage", query.stage);
  if (query.search) params.set("search", query.search);
  params.set("page", String(query.page ?? 1));
  params.set("limit", String(query.limit ?? DEFAULT_LIST_LIMIT));
  return params.toString();
}

export const recordsService = {
  list(query: RecordsQuery = {}): Promise<RecordsListResponse> {
    return http.get<RecordsListResponse>(`/records?${buildQuery(query)}`);
  },

  getById(id: string): Promise<Candidate> {
    return http.get<Candidate>(`/records/${id}`);
  },

  create(payload: CandidateCreatePayload): Promise<Candidate> {
    return http.post<Candidate>("/records", payload);
  },

  replace(id: string, payload: CandidateCreatePayload): Promise<Candidate> {
    return http.put<Candidate>(`/records/${id}`, payload);
  },

  patch(id: string, payload: CandidatePatchPayload): Promise<Candidate> {
    return http.patch<Candidate>(`/records/${id}`, payload);
  },

  remove(id: string): Promise<void> {
    return http.delete<void>(`/records/${id}`);
  },

  listNotes(id: string): Promise<NotesListResponse> {
    return http.get<NotesListResponse>(`/records/${id}/notes`);
  },

  addNote(id: string, payload: NoteCreatePayload): Promise<Note> {
    return http.post<Note>(`/records/${id}/notes`, payload);
  },

  deleteNote(id: string, noteId: string): Promise<void> {
    return http.delete<void>(`/records/${id}/notes/${noteId}`);
  },
};
