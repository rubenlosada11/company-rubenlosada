"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { EXIT_TYPES, exitTypeLabel, warehouseLabel } from "@/lib/data/inventory";
import { ApiError } from "@/lib/http";
import {
  EMPTY_OUTBOUND_DRAFT,
  exceedsStockMessage,
  formatQuantity,
  inventoryApi,
  inventoryErrorMessage,
  inventoryFieldErrors,
  OUTBOUND_FIELDS,
  type OutboundDraft,
  type OutboundField,
  parseInsufficientStock,
  parseQuantity,
  parseSkuId,
  TRACKING_MAX_LENGTH,
  validateOutboundDraft,
} from "@/lib/inventory";
import { useFormTelemetry } from "@/lib/useFormTelemetry";
import type { Product, StockExit } from "@/types/inventory";
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

const fieldId = (field: OutboundField) => `outbound-${field}`;
const errorId = (field: OutboundField) => `outbound-${field}-error`;
const isFormField = (field: string): field is OutboundField => (OUTBOUND_FIELDS as readonly string[]).includes(field);

const DRAFT_TO_FIELD: Record<keyof OutboundDraft, OutboundField> = {
  skuId: "sku_id",
  quantity: "quantity",
  exitType: "exit_type",
  trackingNumber: "tracking_number",
};

interface Created {
  exit: StockExit;
  product: Product | undefined;
  /** Stock tras la salida, consultado a la API; `null` si esa consulta falló. */
  stockAfter: number | null;
}

/**
 * Registro de un despacho o una pérdida (`POST /inventory/orders/outbound`).
 *
 * Salvaguarda de interfaz: el stock del producto elegido se pide a la API al seleccionarlo y, si la cantidad lo
 * supera, se avisa junto al campo y no se deja enviar. Es una ayuda, no la regla: la API vuelve a comprobarlo al
 * registrar la salida (regla 2) y su 400 se muestra en el mismo campo.
 */
export function OutboundForm({ initialSkuId }: { initialSkuId: number | null }) {
  const products = useProducts();
  const telemetry = useFormTelemetry("inventory_outbound", "inventory_outbound");
  const [draft, setDraft] = useState<OutboundDraft>({
    ...EMPTY_OUTBOUND_DRAFT,
    skuId: initialSkuId ? String(initialSkuId) : "",
  });
  const [errors, setErrors] = useState<Partial<Record<OutboundField, string>>>({});
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [focusRequest, setFocusRequest] = useState<{ target: OutboundField | "success" | "alert" } | null>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  const linkedMissing =
    initialSkuId !== null &&
    draft.skuId === String(initialSkuId) &&
    !products.loading &&
    products.error === null &&
    !products.products.some((product) => product.id === initialSkuId);
  const selectedId = linkedMissing ? null : parseSkuId(draft.skuId);
  const selected = products.products.find((product) => product.id === selectedId);
  const { stock, refresh: refreshStock } = useProductStock(selectedId);

  // Solo hay dato fiable cuando la API acaba de responder para el producto elegido (nunca el del producto anterior).
  const available = stock.status === "ready" ? stock.product.current_stock : null;
  const requested = parseQuantity(draft.quantity);
  const soldOut = available !== null && available <= 0;
  const exceeds = available !== null && requested !== null && requested > available;
  const blockedByStock = soldOut || exceeds;

  useEffect(() => {
    if (!focusRequest) return;
    if (focusRequest.target === "success") successRef.current?.focus();
    else if (focusRequest.target === "alert") alertRef.current?.focus();
    else document.getElementById(fieldId(focusRequest.target))?.focus();
  }, [focusRequest]);

  function clearErrors(...fields: OutboundField[]) {
    setErrors((current) => {
      if (!fields.some((field) => current[field])) return current;
      const rest = { ...current };
      for (const field of fields) delete rest[field];
      return rest;
    });
  }

  function update<K extends keyof OutboundDraft>(key: K, value: OutboundDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    const field = DRAFT_TO_FIELD[key];
    telemetry.fieldChanged(field);
    // Un error de stock era del producto anterior: al cambiar de producto deja de valer.
    if (field === "sku_id") clearErrors("sku_id", "quantity");
    else if (field === "exit_type") clearErrors("exit_type", "tracking_number");
    else clearErrors(field);
  }

  function showErrors(fieldErrors: Partial<Record<OutboundField, string>>, message: string | null) {
    setErrors(fieldErrors);
    setFormMessage(message);
    const first = OUTBOUND_FIELDS.find((field) => fieldErrors[field]);
    setFocusRequest({ target: first ?? "alert" });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;

    setCreated(null);
    const { payload, errors: clientErrors } = validateOutboundDraft(
      linkedMissing ? { ...draft, skuId: "" } : draft,
      available
    );
    if (!payload) {
      telemetry.validationFailed(OUTBOUND_FIELDS.filter((field) => clientErrors[field]));
      showErrors(clientErrors, "Revisa los campos marcados antes de registrar la salida.");
      return;
    }

    setErrors({});
    setFormMessage(null);
    submittingRef.current = true;
    setSubmitting(true);
    telemetry.submitStarted();
    try {
      const exit = await inventoryApi.createOutbound(payload, telemetry.reserveRequestId());
      telemetry.submitted(null, 201);
      const after = await inventoryApi.getProduct(exit.sku_id).catch(() => null);
      setCreated({ exit, product: after ?? selected, stockAfter: after?.current_stock ?? null });
      setDraft(EMPTY_OUTBOUND_DRAFT);
      setFocusRequest({ target: "success" });
    } catch (error) {
      telemetry.submitted(error);
      const fieldErrors: Partial<Record<OutboundField, string>> = {};
      for (const [field, message] of Object.entries(inventoryFieldErrors(error))) {
        if (isFormField(field)) fieldErrors[field] = message;
      }
      if (parseInsufficientStock(error)) {
        // El stock ha cambiado desde que se consultó (otra salida, otro puesto): se vuelve a pedir y el error queda
        // junto a la cantidad, sin limpiar nada, hasta que se corrija.
        refreshStock();
        showErrors(fieldErrors, null);
      } else {
        if (error instanceof ApiError && error.status === 404) products.reload();
        showErrors(fieldErrors, inventoryErrorMessage(error, "registrar la salida"));
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  const describedBy = (field: OutboundField, ...extra: (string | null)[]) =>
    [errors[field] ? errorId(field) : null, ...extra].filter(Boolean).join(" ") || undefined;
  const invalid = (field: OutboundField, also = false) => (errors[field] || also ? true : undefined);
  const warehouseName = stock.status === "ready" ? warehouseLabel(stock.product.warehouse) : null;
  // Si la API ya ha respondido con un error de stock en la cantidad, ese mensaje sustituye al aviso local.
  const showWarning = blockedByStock && !errors.quantity;

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby="outbound-form-title"
      aria-busy={submitting}
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
    >
      <h2 id="outbound-form-title" className="font-heading text-xl text-slate-900">
        Datos de la salida
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        La salida se registra en el almacén del producto, con la fecha y la hora actuales y a tu nombre. El número de
        seguimiento solo se pide en los despachos.
      </p>

      {created ? (
        <div
          ref={successRef}
          tabIndex={-1}
          role="status"
          className="mt-5 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-emerald-900 focus:outline-2 focus:outline-offset-2 focus:outline-emerald-600"
        >
          <p className="font-bold">
            Salida n.º {created.exit.id} registrada ({exitTypeLabel(created.exit.exit_type).toLowerCase()})
          </p>
          <p className="mt-1 text-sm">
            {formatQuantity(created.exit.quantity)} {created.exit.quantity === 1 ? "unidad" : "unidades"}
            {created.product ? ` de ${created.product.name} (${created.product.sku})` : ""} desde{" "}
            {warehouseLabel(created.exit.warehouse)}.
            {created.exit.tracking_number ? ` Seguimiento: ${created.exit.tracking_number}.` : ""}
            {created.stockAfter !== null ? ` Stock restante: ${formatQuantity(created.stockAfter)}.` : ""}
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

        <StockPanel stock={stock} id="outbound-stock" />

        <fieldset className="flex flex-col gap-2" aria-describedby={describedBy("exit_type")}>
          <legend className={`${labelClasses} mb-2`}>Tipo de salida</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {EXIT_TYPES.map((type, index) => (
              <label
                key={type.value}
                className={`flex min-h-12 cursor-pointer items-start gap-3 rounded-xl border bg-white p-4 transition has-checked:border-blue-600 has-checked:bg-blue-50 has-focus-visible:ring-2 has-focus-visible:ring-blue-300 ${
                  errors.exit_type ? "border-red-500" : "border-slate-300"
                }`}
              >
                <input
                  id={index === 0 ? fieldId("exit_type") : undefined}
                  type="radio"
                  name="outbound-exit-type"
                  value={type.value}
                  checked={draft.exitType === type.value}
                  onChange={() => update("exitType", type.value)}
                  disabled={submitting}
                  className="mt-0.5 size-5 shrink-0 accent-blue-700"
                />
                <span>
                  <span className="block text-base font-bold text-slate-900">{type.label}</span>
                  <span className="mt-0.5 block text-sm text-slate-600">{type.hint}</span>
                </span>
              </label>
            ))}
          </div>
          <FieldError id={errorId("exit_type")} message={errors.exit_type} />
        </fieldset>

        {draft.exitType === "dispatch" ? (
          <div className="flex flex-col gap-2">
            <label htmlFor={fieldId("tracking_number")} className={labelClasses}>
              Número de seguimiento del transportista
            </label>
            <input
              id={fieldId("tracking_number")}
              value={draft.trackingNumber}
              onChange={(event) => update("trackingNumber", event.target.value)}
              maxLength={TRACKING_MAX_LENGTH}
              autoComplete="off"
              required
              disabled={submitting}
              aria-invalid={invalid("tracking_number")}
              aria-describedby={describedBy("tracking_number")}
              className={inputClasses}
            />
            <FieldError id={errorId("tracking_number")} message={errors.tracking_number} />
          </div>
        ) : null}

        <div className="flex flex-col gap-2">
          <label htmlFor={fieldId("quantity")} className={labelClasses}>
            Cantidad
          </label>
          <input
            id={fieldId("quantity")}
            value={draft.quantity}
            onChange={(event) => update("quantity", event.target.value)}
            inputMode="numeric"
            autoComplete="off"
            required
            disabled={submitting}
            aria-invalid={invalid("quantity", blockedByStock)}
            aria-describedby={describedBy(
              "quantity",
              showWarning ? "outbound-quantity-warning" : null,
              "outbound-quantity-hint"
            )}
            className={`${inputClasses} md:max-w-xs`}
          />
          <FieldError id={errorId("quantity")} message={errors.quantity} />
          {showWarning ? (
            <p
              id="outbound-quantity-warning"
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900"
            >
              <span aria-hidden="true">⚠</span>
              {soldOut
                ? `Este producto está agotado en ${warehouseName}: no hay unidades para registrar una salida.`
                : `${exceedsStockMessage(available ?? 0)} Reduce la cantidad para poder registrar la salida.`}
            </p>
          ) : null}
          <p id="outbound-quantity-hint" className="text-sm text-slate-600">
            Unidades que salen: número entero mayor que 0 y como máximo el stock actual. La API vuelve a comprobar el
            stock al registrar la salida y es quien tiene la última palabra.
          </p>
        </div>
      </div>

      <div className="mt-7">
        <button
          type="submit"
          disabled={submitting || blockedByStock}
          aria-describedby={showWarning ? "outbound-quantity-warning" : undefined}
          className={submitClasses}
        >
          {submitting ? "Registrando…" : "Registrar salida"}
        </button>
      </div>
    </form>
  );
}
