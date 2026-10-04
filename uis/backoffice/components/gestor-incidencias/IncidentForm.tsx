"use client";

import { useEffect, useRef, useState } from "react";
import { INCIDENT_BRANCHES, INCIDENT_CATEGORIES, INCIDENT_ORIGINS } from "@/lib/data/incidents";
import { ApiError } from "@/lib/http";
import {
  DESCRIPTION_MAX_LENGTH,
  EMPTY_INCIDENT_DRAFT,
  INCIDENT_FIELDS,
  type IncidentDraft,
  type IncidentField,
  incidentErrorMessage,
  incidentsApi,
  TITLE_MAX_LENGTH,
  validateIncidentDraft,
} from "@/lib/incidents";
import type { Incident } from "@/types/incidents";

// Controles altos (48 px) y texto de 16 px: el formulario se usa en terminales táctiles del almacén.
const inputClasses =
  "min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 shadow-sm transition focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none aria-invalid:border-red-500 aria-invalid:bg-red-50";
const labelClasses = "text-sm font-bold text-slate-700";

const fieldId = (field: IncidentField) => `incident-${field}`;
const errorId = (field: IncidentField) => `incident-${field}-error`;
const isFormField = (field: string): field is IncidentField => (INCIDENT_FIELDS as readonly string[]).includes(field);

function FieldError({ field, message }: { field: IncidentField; message?: string }) {
  if (!message) return null;
  return (
    <p id={errorId(field)} className="text-sm font-semibold text-red-700">
      {message}
    </p>
  );
}

export function IncidentForm() {
  const [draft, setDraft] = useState<IncidentDraft>(EMPTY_INCIDENT_DRAFT);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [created, setCreated] = useState<Incident | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // El estado tarda un render en deshabilitar el botón: la referencia bloquea un segundo envío inmediato.
  const submittingRef = useRef(false);
  const [focusRequest, setFocusRequest] = useState<{ target: IncidentField | "success" | "alert" } | null>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // El foco se mueve después del render, cuando el mensaje o el campo con error ya están en la página.
  useEffect(() => {
    if (!focusRequest) return;
    if (focusRequest.target === "success") successRef.current?.focus();
    else if (focusRequest.target === "alert") alertRef.current?.focus();
    else document.getElementById(fieldId(focusRequest.target))?.focus();
  }, [focusRequest]);

  function update<K extends keyof IncidentDraft>(field: K, value: IncidentDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    // Al corregir un campo se retira su error; el resto se mantiene hasta el siguiente envío.
    setErrors((current) => {
      if (!current[field]) return current;
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
  }

  function showErrors(fieldErrors: Record<string, string>, message: string | null) {
    setErrors(fieldErrors);
    setFormMessage(message);
    const first = INCIDENT_FIELDS.find((field) => fieldErrors[field]);
    setFocusRequest({ target: first ?? "alert" });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;

    setCreated(null);
    const { payload, errors: clientErrors } = validateIncidentDraft(draft);
    if (!payload) {
      showErrors(clientErrors, "Revisa los campos marcados antes de registrar la incidencia.");
      return;
    }

    setErrors({});
    setFormMessage(null);
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const incident = await incidentsApi.create(payload);
      setDraft(EMPTY_INCIDENT_DRAFT);
      setCreated(incident);
      setFocusRequest({ target: "success" });
    } catch (error) {
      const fieldErrors: Record<string, string> = {};
      if (error instanceof ApiError && (error.status === 400 || error.status === 422)) {
        for (const [field, message] of Object.entries(error.fieldErrors)) {
          if (isFormField(field)) fieldErrors[field] = message;
        }
      }
      showErrors(fieldErrors, incidentErrorMessage(error, "registrar la incidencia"));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  const describedBy = (field: IncidentField, extra?: string) =>
    [errors[field] ? errorId(field) : null, extra].filter(Boolean).join(" ") || undefined;
  const invalid = (field: IncidentField) => (errors[field] ? true : undefined);
  const branchHighlighted = draft.origin === "branch";

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby="incident-form-title"
      aria-busy={submitting}
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
    >
      <h2 id="incident-form-title" className="font-heading text-xl text-slate-900">
        Datos de la incidencia
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Todos los campos son obligatorios. La incidencia se registra como abierta, con la fecha y la hora actuales.
      </p>

      {created ? (
        <div
          ref={successRef}
          tabIndex={-1}
          role="status"
          className="mt-5 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-emerald-900 focus:outline-2 focus:outline-offset-2 focus:outline-emerald-600"
        >
          <p className="font-bold">Incidencia n.º {created.id} registrada</p>
          <p className="mt-1 text-sm">«{created.title}». Puedes registrar otra con este mismo formulario.</p>
        </div>
      ) : null}

      {formMessage ? (
        <div
          ref={alertRef}
          tabIndex={-1}
          role="alert"
          className="mt-5 rounded-xl border border-red-300 bg-red-50 p-4 text-sm font-semibold text-red-800 focus:outline-2 focus:outline-offset-2 focus:outline-red-600"
        >
          {formMessage}
        </div>
      ) : null}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="flex flex-col gap-2 md:col-span-2">
          <label htmlFor={fieldId("title")} className={labelClasses}>
            Título
          </label>
          <input
            id={fieldId("title")}
            value={draft.title}
            onChange={(event) => update("title", event.target.value)}
            maxLength={TITLE_MAX_LENGTH}
            autoComplete="off"
            required
            aria-invalid={invalid("title")}
            aria-describedby={describedBy("title", "incident-title-hint")}
            className={inputClasses}
          />
          <div className="flex items-start justify-between gap-3">
            <FieldError field="title" message={errors.title} />
            <p id="incident-title-hint" className="ml-auto shrink-0 text-xs text-slate-500">
              {draft.title.length} / {TITLE_MAX_LENGTH}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 md:col-span-2">
          <label htmlFor={fieldId("description")} className={labelClasses}>
            Descripción
          </label>
          <textarea
            id={fieldId("description")}
            rows={4}
            value={draft.description}
            onChange={(event) => update("description", event.target.value)}
            maxLength={DESCRIPTION_MAX_LENGTH}
            required
            aria-invalid={invalid("description")}
            aria-describedby={describedBy("description")}
            className={inputClasses}
          />
          <FieldError field="description" message={errors.description} />
        </div>

        <div className="flex flex-col gap-2 md:col-span-2">
          <label htmlFor={fieldId("category")} className={labelClasses}>
            Categoría
          </label>
          <select
            id={fieldId("category")}
            value={draft.category}
            onChange={(event) => update("category", event.target.value as IncidentDraft["category"])}
            required
            aria-invalid={invalid("category")}
            aria-describedby={describedBy("category")}
            className={inputClasses}
          >
            <option value="">Elige una categoría</option>
            {INCIDENT_CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>
                {category.label}
              </option>
            ))}
          </select>
          <FieldError field="category" message={errors.category} />
        </div>

        <fieldset
          className="flex flex-col gap-2 md:col-span-2"
          aria-invalid={invalid("origin")}
          aria-describedby={describedBy("origin")}
        >
          <legend className={`${labelClasses} mb-2`}>Origen</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {INCIDENT_ORIGINS.map((origin, index) => (
              <label
                key={origin.value}
                className={`flex min-h-12 cursor-pointer items-start gap-3 rounded-xl border bg-white p-4 transition has-checked:border-blue-600 has-checked:bg-blue-50 has-focus-visible:ring-2 has-focus-visible:ring-blue-300 ${
                  errors.origin ? "border-red-500" : "border-slate-300"
                }`}
              >
                <input
                  // El primer radio lleva el id del campo: es donde se pone el foco si el origen tiene un error.
                  id={index === 0 ? fieldId("origin") : undefined}
                  type="radio"
                  name="incident-origin"
                  value={origin.value}
                  checked={draft.origin === origin.value}
                  onChange={() => update("origin", origin.value)}
                  className="mt-0.5 size-5 shrink-0 accent-blue-700"
                />
                <span>
                  <span className="block text-base font-bold text-slate-900">{origin.label}</span>
                  <span className="mt-0.5 block text-sm text-slate-600">{origin.hint}</span>
                </span>
              </label>
            ))}
          </div>
          <FieldError field="origin" message={errors.origin} />
        </fieldset>

        <div
          data-highlighted={branchHighlighted}
          className={`flex flex-col gap-2 rounded-xl transition-all md:col-span-2 ${
            branchHighlighted ? "border-2 border-blue-600 bg-blue-50 p-4" : "border-2 border-transparent"
          }`}
        >
          <label htmlFor={fieldId("branch")} className={labelClasses}>
            Sede
            {branchHighlighted ? (
              <span className="ml-2 rounded-full bg-blue-700 px-2.5 py-0.5 text-xs font-bold text-white">
                Sede que reporta
              </span>
            ) : null}
          </label>
          <select
            id={fieldId("branch")}
            value={draft.branch}
            onChange={(event) => update("branch", event.target.value as IncidentDraft["branch"])}
            required
            aria-invalid={invalid("branch")}
            aria-describedby={describedBy("branch", "incident-branch-hint")}
            className={inputClasses}
          >
            <option value="">Elige una sede</option>
            {INCIDENT_BRANCHES.map((branch) => (
              <option key={branch.value} value={branch.value}>
                {branch.label}
              </option>
            ))}
          </select>
          <FieldError field="branch" message={errors.branch} />
          <p
            id="incident-branch-hint"
            className={`text-sm ${branchHighlighted ? "font-semibold text-blue-900" : "text-slate-600"}`}
          >
            {branchHighlighted
              ? "El origen es una sede: indica el almacén u oficina donde se ha detectado la incidencia."
              : "Si la incidencia no corresponde a una instalación concreta, elige «Central»."}
          </p>
        </div>
      </div>

      <div className="mt-7">
        <button
          type="submit"
          disabled={submitting}
          className="min-h-12 w-full rounded-full bg-blue-700 px-8 py-3 text-base font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
        >
          {submitting ? "Registrando…" : "Registrar incidencia"}
        </button>
      </div>
    </form>
  );
}
