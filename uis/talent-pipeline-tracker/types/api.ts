/**
 * Tipos correspondientes al esquema real de la API (verificado contra
 * https://playground.4geeks.com/tracker/api/v1/openapi.json y respuestas en vivo).
 */

export type CandidateStatus = "received" | "in_progress" | "selected" | "discarded";

export type CandidateStage =
  | "pending"
  | "review"
  | "personal_interview"
  | "technical_interview"
  | "offer_presented";

export interface Note {
  id: string;
  record_id: string;
  content: string;
  created_at: string;
}

/** Forma devuelta por GET /records (incluye notas embebidas). */
export interface CandidateListItem {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  experience_years: number;
  status: CandidateStatus;
  stage: CandidateStage;
  notes_count: number;
  applied_at: string;
  updated_at: string;
  notes: Note[];
}

/** Forma devuelta por GET /records/:id (sin notas embebidas). */
export interface Candidate {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  experience_years: number;
  status: CandidateStatus;
  stage: CandidateStage;
  notes_count: number;
  applied_at: string;
  updated_at: string;
}

export interface RecordsListResponse {
  total: number;
  page: number;
  limit: number;
  data: CandidateListItem[];
}

export interface NotesListResponse {
  data: Note[];
  meta: { total: number };
}

/** Payload para POST /records y PUT /records/:id (RecordCreate en la API). */
export interface CandidateCreatePayload {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  experience_years: number;
  linkedin_url: string | null;
  cv_url: string | null;
}

/** Payload para PATCH /records/:id (RecordPatch en la API). */
export interface CandidatePatchPayload {
  status?: CandidateStatus;
  stage?: CandidateStage;
}

export interface NoteCreatePayload {
  content: string;
}

export interface RecordsQuery {
  status?: CandidateStatus;
  stage?: CandidateStage;
  search?: string;
  page?: number;
  limit?: number;
}
