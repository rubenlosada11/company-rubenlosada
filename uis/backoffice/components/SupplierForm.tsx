"use client";

import { useState } from "react";
import { CURRENCY_BY_COUNTRY, SUPPLIER_CATEGORIES, SUPPLIER_COUNTRIES, SUPPLIER_STATUSES } from "@/lib/data/suppliers";
import { ApiError, apiErrorMessage, FORM_ERROR } from "@/lib/http";
import { EMPTY_DRAFT, type SupplierDraft, suppliersApi, validateDraft } from "@/lib/suppliers";
import type { Supplier, SupplierCategory } from "@/types";

const inputClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none aria-invalid:border-red-400";
const labelClasses = "text-xs font-bold tracking-wide text-slate-500 uppercase";

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs font-semibold text-red-700">
      {message}
    </p>
  );
}

interface SupplierFormProps {
  onCreated: (supplier: Supplier) => void;
  onCancel: () => void;
}

export function SupplierForm({ onCreated, onCancel }: SupplierFormProps) {
  const [draft, setDraft] = useState<SupplierDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverMessage, setServerMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const currency = draft.country ? CURRENCY_BY_COUNTRY[draft.country] : null;

  function update<K extends keyof SupplierDraft>(field: K, value: SupplierDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  function toggleCategory(category: SupplierCategory) {
    update(
      "categories",
      draft.categories.includes(category)
        ? draft.categories.filter((item) => item !== category)
        : [...draft.categories, category]
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setServerMessage(null);
    const { payload, errors: clientErrors } = validateDraft(draft);
    setErrors(clientErrors);
    if (!payload) return;

    setSubmitting(true);
    try {
      const created = await suppliersApi.create(payload);
      setDraft(EMPTY_DRAFT);
      onCreated(created);
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length > 0) {
        // Datos rechazados: cada error va en su campo; el aviso general solo lleva el que no es de ningún campo.
        setErrors(error.fieldErrors);
        setServerMessage(error.fieldErrors[FORM_ERROR] ?? "Revisa los campos marcados y vuelve a intentarlo.");
      } else {
        setServerMessage(apiErrorMessage(error, "registrar el proveedor"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const describedBy = (field: string) => (errors[field] ? `new-supplier-${field}-error` : undefined);
  const invalid = (field: string) => (errors[field] ? true : undefined);

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby="new-supplier-title"
      aria-busy={submitting}
      className="rounded-2xl border border-blue-200 bg-white p-5 shadow-sm"
    >
      <h3 id="new-supplier-title" className="font-heading text-lg text-slate-900">
        Registrar proveedor
      </h3>
      <p className="mt-1 text-sm text-slate-600">
        La moneda la fija el país del contrato. La fecha de actualización la genera la API.
      </p>

      {serverMessage || errors[FORM_ERROR] ? (
        <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {serverMessage ?? errors[FORM_ERROR]}
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5 md:col-span-2">
          <label htmlFor="new-supplier-name" className={labelClasses}>
            Nombre *
          </label>
          <input
            id="new-supplier-name"
            value={draft.name}
            onChange={(event) => update("name", event.target.value)}
            aria-invalid={invalid("name")}
            aria-describedby={describedBy("name")}
            className={inputClasses}
          />
          <FieldError id="new-supplier-name-error" message={errors.name} />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-supplier-country" className={labelClasses}>
            País del contrato *
          </label>
          <select
            id="new-supplier-country"
            value={draft.country}
            onChange={(event) => update("country", event.target.value as SupplierDraft["country"])}
            aria-invalid={invalid("country")}
            aria-describedby={describedBy("country")}
            className={inputClasses}
          >
            <option value="">Elige un país</option>
            {SUPPLIER_COUNTRIES.map((country) => (
              <option key={country.value} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
          <FieldError id="new-supplier-country-error" message={errors.country ?? errors.currency} />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-supplier-rate" className={labelClasses}>
            Tarifa por envío * {currency ? `(${currency})` : ""}
          </label>
          <input
            id="new-supplier-rate"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            value={draft.rate}
            onChange={(event) => update("rate", event.target.value)}
            aria-invalid={invalid("rate_per_shipment")}
            aria-describedby={describedBy("rate_per_shipment")}
            className={inputClasses}
          />
          <FieldError id="new-supplier-rate_per_shipment-error" message={errors.rate_per_shipment} />
        </div>

        <fieldset
          className="flex flex-col gap-2 md:col-span-2"
          aria-invalid={invalid("categories")}
          aria-describedby={describedBy("categories")}
        >
          <legend className={`${labelClasses} mb-2`}>Categorías * (una o varias)</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {SUPPLIER_CATEGORIES.map((category) => (
              <label
                key={category.value}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 has-checked:border-blue-400 has-checked:bg-blue-50"
              >
                <input
                  type="checkbox"
                  checked={draft.categories.includes(category.value)}
                  onChange={() => toggleCategory(category.value)}
                  className="size-4 accent-blue-700"
                />
                {category.label}
              </label>
            ))}
          </div>
          <FieldError id="new-supplier-categories-error" message={errors.categories} />
        </fieldset>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-supplier-status" className={labelClasses}>
            Estado *
          </label>
          <select
            id="new-supplier-status"
            value={draft.status}
            onChange={(event) => update("status", event.target.value as SupplierDraft["status"])}
            aria-invalid={invalid("status")}
            aria-describedby={describedBy("status")}
            className={inputClasses}
          >
            {SUPPLIER_STATUSES.map((status) => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </select>
          <FieldError id="new-supplier-status-error" message={errors.status} />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-supplier-zone" className={labelClasses}>
            Zona de servicio
          </label>
          <input
            id="new-supplier-zone"
            value={draft.service_zone}
            onChange={(event) => update("service_zone", event.target.value)}
            placeholder="p. ej. West Coast, Aragón"
            className={inputClasses}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-supplier-email" className={labelClasses}>
            Email de contacto
          </label>
          <input
            id="new-supplier-email"
            type="email"
            value={draft.contact_email}
            onChange={(event) => update("contact_email", event.target.value)}
            aria-invalid={invalid("contact_email")}
            aria-describedby={describedBy("contact_email")}
            className={inputClasses}
          />
          <FieldError id="new-supplier-contact_email-error" message={errors.contact_email} />
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <label htmlFor="new-supplier-notes" className={labelClasses}>
            Notas
          </label>
          <textarea
            id="new-supplier-notes"
            rows={2}
            value={draft.notes}
            onChange={(event) => update("notes", event.target.value)}
            className={inputClasses}
          />
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-60"
        >
          {submitting ? "Registrando…" : "Registrar proveedor"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
