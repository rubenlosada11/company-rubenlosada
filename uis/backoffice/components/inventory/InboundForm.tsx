"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { warehouseLabel } from "@/lib/data/inventory";
import { ApiError } from "@/lib/http";
import {
  EMPTY_INBOUND_DRAFT,
  formatQuantity,
  INBOUND_FIELDS,
  type InboundDraft,
  type InboundField,
  inventoryApi,
  inventoryErrorMessage,
  inventoryFieldErrors,
  parseSkuId,
  REFERENCE_MAX_LENGTH,
  validateInboundDraft,
} from "@/lib/inventory";
import { useFormTelemetry } from "@/lib/useFormTelemetry";
import type { Product, StockEntry } from "@/types/inventory";
import {
  FieldError,
  inputClasses,
  labelClasses,
  ProductSelect,
  StockPanel,
  submitClasses,
  useProducts,
  useProductStock,
} from "./formParts";

const fieldId = (field: InboundField) => `inbound-${field}`;
const errorId = (field: InboundField) => `inbound-${field}-error`;
const isFormField = (field: string): field is InboundField => (INBOUND_FIELDS as readonly string[]).includes(field);

interface Created {
  entry: StockEntry;
  product: Product | undefined;
  /** Stock tras la entrada, consultado a la API; `null` si esa consulta falló. */
  stockAfter: number | null;
}

/** Registro de una recepción de mercancía (`POST /inventory/orders/inbound`). */
export function InboundForm({ initialSkuId }: { initialSkuId: number | null }) {
  const products = useProducts();
  const telemetry = useFormTelemetry("inventory_inbound", "inventory_inbound");
  const [draft, setDraft] = useState<InboundDraft>({
    ...EMPTY_INBOUND_DRAFT,
    skuId: initialSkuId ? String(initialSkuId) : "",
  });
  const [errors, setErrors] = useState<Partial<Record<InboundField, string>>>({});
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // El estado tarda un render en deshabilitar el botón: la referencia bloquea un segundo envío inmediato.
  const submittingRef = useRef(false);
  const [focusRequest, setFocusRequest] = useState<{ target: InboundField | "success" | "alert" } | null>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // El producto del enlace (`?sku_id=`) solo vale si existe en el inventario; si no, se avisa y se elige a mano.
  const linkedMissing =
    initialSkuId !== null &&
    draft.skuId === String(initialSkuId) &&
    !products.loading &&
    products.error === null &&
    !products.products.some((product) => product.id === initialSkuId);
  const selectedId = linkedMissing ? null : parseSkuId(draft.skuId);
  const selected = products.products.find((product) => product.id === selectedId);
  const { stock } = useProductStock(selectedId);

  useEffect(() => {
    if (!focusRequest) return;
    if (focusRequest.target === "success") successRef.current?.focus();
    else if (focusRequest.target === "alert") alertRef.current?.focus();
    else document.getElementById(fieldId(focusRequest.target))?.focus();
  }, [focusRequest]);

  function update<K extends keyof InboundDraft>(key: K, value: InboundDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    const field: InboundField = key === "skuId" ? "sku_id" : (key as InboundField);
    telemetry.fieldChanged(field);
    setErrors((current) => {
      if (!current[field]) return current;
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
  }

  function showErrors(fieldErrors: Partial<Record<InboundField, string>>, message: string | null) {
    setErrors(fieldErrors);
    setFormMessage(message);
    const first = INBOUND_FIELDS.find((field) => fieldErrors[field]);
    setFocusRequest({ target: first ?? "alert" });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;

    setCreated(null);
    const { payload, errors: clientErrors } = validateInboundDraft(linkedMissing ? { ...draft, skuId: "" } : draft);
    if (!payload) {
      telemetry.validationFailed(INBOUND_FIELDS.filter((field) => clientErrors[field]));
      showErrors(clientErrors, "Revisa los campos marcados antes de registrar la entrada.");
      return;
    }

    setErrors({});
    setFormMessage(null);
    submittingRef.current = true;
    setSubmitting(true);
    telemetry.submitStarted();
    try {
      const entry = await inventoryApi.createInbound(payload, telemetry.reserveRequestId());
      telemetry.submitted(null, 201);
      // Stock actualizado para la confirmación. Si esta consulta falla, la entrada ya está registrada igualmente.
      const after = await inventoryApi.getProduct(entry.sku_id).catch(() => null);
      setCreated({ entry, product: after ?? selected, stockAfter: after?.current_stock ?? null });
      setDraft(EMPTY_INBOUND_DRAFT);
      setFocusRequest({ target: "success" });
    } catch (error) {
      telemetry.submitted(error);
      const fieldErrors: Partial<Record<InboundField, string>> = {};
      for (const [field, message] of Object.entries(inventoryFieldErrors(error))) {
        if (isFormField(field)) fieldErrors[field] = message;
      }
      // El producto ya no existe: se recarga el selector para no ofrecerlo de nuevo.
      if (error instanceof ApiError && error.status === 404) products.reload();
      showErrors(fieldErrors, inventoryErrorMessage(error, "registrar la entrada"));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  const describedBy = (field: InboundField, extra?: string) =>
    [errors[field] ? errorId(field) : null, extra].filter(Boolean).join(" ") || undefined;
  const invalid = (field: InboundField) => (errors[field] ? true : undefined);

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby="inbound-form-title"
      aria-busy={submitting}
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
    >
      <h2 id="inbound-form-title" className="font-heading text-xl text-slate-900">
        Datos de la recepción
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Todos los campos son obligatorios. La entrada se registra en el almacén del producto, con la fecha y la hora
        actuales y a tu nombre.
      </p>

      {created ? (
        <div
          ref={successRef}
          tabIndex={-1}
          role="status"
          className="mt-5 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-emerald-900 focus:outline-2 focus:outline-offset-2 focus:outline-emerald-600"
        >
          <p className="font-bold">Entrada n.º {created.entry.id} registrada</p>
          <p className="mt-1 text-sm">
            {formatQuantity(created.entry.quantity)} {created.entry.quantity === 1 ? "unidad" : "unidades"}
            {created.product ? ` de ${created.product.name} (${created.product.sku})` : ""} en{" "}
            {warehouseLabel(created.entry.warehouse)}. Referencia: {created.entry.reference}.
            {created.stockAfter !== null ? ` Stock actual: ${formatQuantity(created.stockAfter)}.` : ""}
          </p>
          <p className="mt-2 text-sm">
            <Link href="/inventory/products" className="font-bold underline underline-offset-2">
              Ver productos y stock
            </Link>{" "}
            ·{" "}
            <Link href="/inventory/orders" className="font-bold underline underline-offset-2">
              Ver historial
            </Link>
          </p>
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

      {linkedMissing ? (
        <p role="status" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          El producto del enlace ya no está en el inventario. Elige uno de la lista.
        </p>
      ) : null}

      <div className="mt-6 grid gap-6">
        <ProductSelect
          id={fieldId("sku_id")}
          value={linkedMissing ? "" : draft.skuId}
          onChange={(value) => update("skuId", value)}
          products={products}
          error={errors.sku_id}
          errorId={errorId("sku_id")}
          disabled={submitting}
        />

        <StockPanel stock={stock} id="inbound-stock" />

        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <label htmlFor={fieldId("quantity")} className={labelClasses}>
              Cantidad recibida
            </label>
            <input
              id={fieldId("quantity")}
              value={draft.quantity}
              onChange={(event) => update("quantity", event.target.value)}
              inputMode="numeric"
              autoComplete="off"
              required
              disabled={submitting}
              aria-invalid={invalid("quantity")}
              aria-describedby={describedBy("quantity", "inbound-quantity-hint")}
              className={inputClasses}
            />
            <FieldError id={errorId("quantity")} message={errors.quantity} />
            <p id="inbound-quantity-hint" className="text-sm text-slate-600">
              Unidades recibidas: número entero mayor que 0.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor={fieldId("reference")} className={labelClasses}>
              Referencia del cliente
            </label>
            <input
              id={fieldId("reference")}
              value={draft.reference}
              onChange={(event) => update("reference", event.target.value)}
              maxLength={REFERENCE_MAX_LENGTH}
              autoComplete="off"
              required
              disabled={submitting}
              aria-invalid={invalid("reference")}
              aria-describedby={describedBy("reference", "inbound-reference-hint")}
              className={inputClasses}
            />
            <FieldError id={errorId("reference")} message={errors.reference} />
            <p id="inbound-reference-hint" className="text-sm text-slate-600">
              Referencia de despacho del cliente, por ejemplo su número de orden de compra.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-7">
        <button type="submit" disabled={submitting} className={submitClasses}>
          {submitting ? "Registrando…" : "Registrar entrada"}
        </button>
      </div>
    </form>
  );
}
