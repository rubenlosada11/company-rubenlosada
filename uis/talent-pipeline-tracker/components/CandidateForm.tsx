"use client";

import { useState, type FormEvent } from "react";
import { InlineError } from "@/components/StateBanner";
import {
  EMPTY_CANDIDATE_FORM,
  validateCandidateForm,
  type CandidateFormErrors,
  type CandidateFormValues,
} from "@/lib/validation";

interface CandidateFormProps {
  mode: "create" | "edit";
  initialValues?: CandidateFormValues;
  submitLabel: string;
  pendingLabel: string;
  isSubmitting: boolean;
  submitError: string | null;
  onSubmit: (values: CandidateFormValues) => void;
  onCancel?: () => void;
}

const inputClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200";

const labelClasses = "text-sm font-semibold text-slate-700";

export function CandidateForm({
  initialValues,
  submitLabel,
  pendingLabel,
  isSubmitting,
  submitError,
  onSubmit,
  onCancel,
}: CandidateFormProps) {
  const [values, setValues] = useState<CandidateFormValues>(initialValues ?? EMPTY_CANDIDATE_FORM);
  const [errors, setErrors] = useState<CandidateFormErrors>({});

  function update<K extends keyof CandidateFormValues>(key: K, value: CandidateFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const validationErrors = validateCandidateForm(values);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;
    onSubmit(values);
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <label className={labelClasses} htmlFor="full_name">
            Nombre completo *
          </label>
          <input
            id="full_name"
            className={inputClasses}
            value={values.full_name}
            onChange={(e) => update("full_name", e.target.value)}
            disabled={isSubmitting}
            autoComplete="name"
          />
          {errors.full_name && <InlineError message={errors.full_name} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="email">
            Email *
          </label>
          <input
            id="email"
            type="email"
            className={inputClasses}
            value={values.email}
            onChange={(e) => update("email", e.target.value)}
            disabled={isSubmitting}
            autoComplete="email"
          />
          {errors.email && <InlineError message={errors.email} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="phone">
            Teléfono *
          </label>
          <input
            id="phone"
            type="tel"
            className={inputClasses}
            value={values.phone}
            onChange={(e) => update("phone", e.target.value)}
            disabled={isSubmitting}
            autoComplete="tel"
          />
          {errors.phone && <InlineError message={errors.phone} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="position">
            Puesto *
          </label>
          <input
            id="position"
            className={inputClasses}
            value={values.position}
            onChange={(e) => update("position", e.target.value)}
            disabled={isSubmitting}
          />
          {errors.position && <InlineError message={errors.position} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="experience_years">
            Años de experiencia *
          </label>
          <input
            id="experience_years"
            type="number"
            min={0}
            step="0.5"
            className={inputClasses}
            value={values.experience_years}
            onChange={(e) => update("experience_years", e.target.value)}
            disabled={isSubmitting}
          />
          {errors.experience_years && <InlineError message={errors.experience_years} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="linkedin_url">
            LinkedIn
          </label>
          <input
            id="linkedin_url"
            type="url"
            placeholder="https://linkedin.com/in/..."
            className={inputClasses}
            value={values.linkedin_url}
            onChange={(e) => update("linkedin_url", e.target.value)}
            disabled={isSubmitting}
          />
          {errors.linkedin_url && <InlineError message={errors.linkedin_url} />}
        </div>

        <div className="space-y-1.5">
          <label className={labelClasses} htmlFor="cv_url">
            CV (URL)
          </label>
          <input
            id="cv_url"
            type="url"
            placeholder="https://..."
            className={inputClasses}
            value={values.cv_url}
            onChange={(e) => update("cv_url", e.target.value)}
            disabled={isSubmitting}
          />
          {errors.cv_url && <InlineError message={errors.cv_url} />}
        </div>
      </div>

      {submitError && <InlineError message={submitError} />}

      <div className="flex flex-wrap items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-900/20 transition hover:-translate-y-0.5 hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
        >
          {isSubmitting ? pendingLabel : submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
}
