import { useEffect, useRef } from "react";
import { ApiError } from "@/lib/http";
import { track } from "@/lib/telemetry";
import type { FormField, FormId, FrontendEventProperties, Section } from "@/lib/telemetryCatalog";
import { reserveFormRequestId } from "@/lib/telemetrySession";

type Outcome = FrontendEventProperties["form_submitted"]["outcome"];

/** Throttle de `form_validation_failed` (doble clic en «Registrar»). */
const VALIDATION_THROTTLE_MS = 2_000;
const MAX_FAILED_FIELDS = 10;
const MAX_ATTEMPTS = 50;

interface Instance {
  startedAt: number | null;
  touched: Set<FormField>;
  lastField: FormField | null;
  attempts: number;
  hadFailedSubmit: boolean;
  submitStartedAt: number | null;
  lastValidationAt: number;
}

const fresh = (): Instance => ({
  startedAt: null,
  touched: new Set(),
  lastField: null,
  attempts: 0,
  hadFailedSubmit: false,
  submitStartedAt: null,
  lastValidationAt: 0,
});

/** Resultado de un envío a partir del error de la API (o `null` si fue bien). */
export function submitOutcome(error: unknown): { outcome: Outcome; httpStatus: number | null } {
  if (error === null) return { outcome: "success", httpStatus: null };
  if (!(error instanceof ApiError) || error.status === 0) return { outcome: "network_error", httpStatus: null };
  const status = error.status;
  if (status === 401 || status === 403) return { outcome: "unauthorized", httpStatus: status };
  if (status === 422) return { outcome: "validation_error", httpStatus: status };
  if (status >= 500 || status < 400) return { outcome: "server_error", httpStatus: status };
  return { outcome: "business_rejection", httpStatus: status }; // 400 (stock insuficiente), 404, 409
}

/**
 * Embudo de un formulario para la telemetría (plan §9.5 y §13.4). Una «instancia» va del primer cambio de un campo a
 * un envío correcto o al abandono:
 *
 * - `form_started`: en el primer cambio de un campo (nunca por pulsación).
 * - `form_validation_failed`: al pulsar enviar con errores locales (solo los nombres de campo; máximo uno cada 2 s).
 * - `form_submitted`: al terminar la llamada a la API, con su resultado, código y duración. El `requestId` lo pone el
 *   servicio (el que reservó `reserveRequestId`), así se une con el evento de negocio de la API.
 * - `form_abandoned`: al salir (desmontaje o `pagehide`) con el formulario empezado y sin un envío correcto.
 *
 * Nunca se envían valores de los campos. Es la capa que sabe qué ha pasado en el formulario; los hechos de negocio
 * (orden registrada, rechazada) los emite la API.
 */
export function useFormTelemetry(formId: FormId, section: Section) {
  const instance = useRef<Instance>(fresh());

  useEffect(() => {
    const abandon = () => {
      const current = instance.current;
      if (current.startedAt === null || current.lastField === null) return;
      track("form_abandoned", {
        form_id: formId,
        duration_ms: Math.max(0, Math.round(performance.now() - current.startedAt)),
        fields_touched_count: Math.min(Math.max(current.touched.size, 1), MAX_ATTEMPTS),
        last_field: current.lastField,
        had_failed_submit: current.hadFailedSubmit,
      });
      instance.current = fresh(); // una sola vez por instancia (pagehide + desmontaje)
    };
    // Fase de captura: antes de que el servicio de telemetría vacíe la cola por beacon en el mismo `pagehide`.
    window.addEventListener("pagehide", abandon, { capture: true });
    return () => {
      window.removeEventListener("pagehide", abandon, { capture: true });
      abandon();
    };
  }, [formId]);

  return {
    /** Un campo ha cambiado (nombre del campo, nunca su valor). */
    fieldChanged(field: FormField) {
      const current = instance.current;
      if (current.startedAt === null) {
        current.startedAt = performance.now();
        track("form_started", { form_id: formId, section });
      }
      current.touched.add(field);
      current.lastField = field;
    },

    /** La validación local ha impedido el envío. */
    validationFailed(fields: FormField[]) {
      const current = instance.current;
      current.attempts = Math.min(current.attempts + 1, MAX_ATTEMPTS);
      current.hadFailedSubmit = true;
      const now = Date.now();
      if (fields.length === 0 || now - current.lastValidationAt < VALIDATION_THROTTLE_MS) return;
      current.lastValidationAt = now;
      track("form_validation_failed", {
        form_id: formId,
        failed_fields: [...new Set(fields)].slice(0, MAX_FAILED_FIELDS),
        attempt_number: current.attempts,
      });
    },

    /** Empieza la llamada a la API. */
    submitStarted() {
      const current = instance.current;
      current.attempts = Math.min(current.attempts + 1, MAX_ATTEMPTS);
      current.submitStartedAt = performance.now();
    },

    /** `X-Request-Id` para la llamada del envío (se une con el `form_submitted`). */
    reserveRequestId(): string {
      return reserveFormRequestId(formId);
    },

    /** Termina la llamada: `error` es `null` si fue bien (con `successStatus`, el código de la respuesta). */
    submitted(error: unknown, successStatus: number | null = null) {
      const current = instance.current;
      const { outcome, httpStatus } = submitOutcome(error);
      const started = current.submitStartedAt;
      track("form_submitted", {
        form_id: formId,
        outcome,
        http_status: outcome === "success" ? successStatus : httpStatus,
        attempt_number: Math.max(current.attempts, 1),
        duration_ms: started === null ? null : Math.round((performance.now() - started) * 100) / 100,
      });
      if (outcome === "success") instance.current = fresh();
      else current.hadFailedSubmit = true;
    },
  };
}
