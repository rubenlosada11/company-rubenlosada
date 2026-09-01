import type { CandidateCreatePayload } from "@/types/api";

export interface CandidateFormValues {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  experience_years: string;
  linkedin_url: string;
  cv_url: string;
}

export type CandidateFormErrors = Partial<Record<keyof CandidateFormValues, string>>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isValidUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function validateCandidateForm(values: CandidateFormValues): CandidateFormErrors {
  const errors: CandidateFormErrors = {};

  if (!values.full_name.trim()) errors.full_name = "El nombre completo es obligatorio.";

  if (!values.email.trim()) errors.email = "El email es obligatorio.";
  else if (!EMAIL_RE.test(values.email.trim())) errors.email = "Introduce un email válido.";

  if (!values.phone.trim()) errors.phone = "El teléfono es obligatorio.";

  if (!values.position.trim()) errors.position = "El puesto es obligatorio.";

  if (!values.experience_years.trim()) {
    errors.experience_years = "Los años de experiencia son obligatorios.";
  } else {
    const parsed = Number(values.experience_years);
    if (Number.isNaN(parsed) || parsed < 0) {
      errors.experience_years = "Introduce un número de años válido (0 o más).";
    }
  }

  if (values.linkedin_url.trim() && !isValidUrl(values.linkedin_url.trim())) {
    errors.linkedin_url = "Si incluyes LinkedIn, debe ser una URL válida (https://...).";
  }

  if (values.cv_url.trim() && !isValidUrl(values.cv_url.trim())) {
    errors.cv_url = "Si incluyes el CV, debe ser una URL válida (https://...).";
  }

  return errors;
}

export function toCreatePayload(values: CandidateFormValues): CandidateCreatePayload {
  return {
    full_name: values.full_name.trim(),
    email: values.email.trim(),
    phone: values.phone.trim(),
    position: values.position.trim(),
    experience_years: Number(values.experience_years),
    linkedin_url: values.linkedin_url.trim() || null,
    cv_url: values.cv_url.trim() || null,
  };
}

export const EMPTY_CANDIDATE_FORM: CandidateFormValues = {
  full_name: "",
  email: "",
  phone: "",
  position: "",
  experience_years: "",
  linkedin_url: "",
  cv_url: "",
};
