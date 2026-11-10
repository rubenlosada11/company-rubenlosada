/**
 * Eventos de telemetría que puede emitir el backoffice, con su allowlist de propiedades.
 *
 * Fuente: `docs/telemetry/event-schemas.json` (catálogo aprobado, versión 1.0.0). Aquí solo están los eventos cuyo
 * `source` admite `frontend`; los de negocio (órdenes de inventario, login…) los emite la API, que es la única que sabe
 * si la operación se ha hecho de verdad. `lib/telemetryCatalog.test.ts` compara este fichero con el JSON: si el catálogo
 * cambia y este no, el test falla.
 *
 * Los tipos obligan a quien llama a `track()` a pasar exactamente las propiedades del contrato; `ALLOWLIST` hace la
 * misma comprobación en ejecución (ninguna clave de más ni de menos).
 */

export const CATALOG_VERSION = "1.0.0";

export const SECTIONS = [
  "dashboard",
  "suppliers",
  "incident_analysis",
  "incident_manager",
  "incident_create",
  "inventory_products",
  "inventory_orders",
  "inventory_inbound",
  "inventory_outbound",
  "account_profile",
  "account_change_password",
  "login",
  "register",
  "forgot_password",
  "reset_password",
  "not_found",
] as const;
export type Section = (typeof SECTIONS)[number];

export const FORM_IDS = [
  "login",
  "register",
  "forgot_password",
  "reset_password",
  "change_password",
  "profile",
  "supplier_create",
  "incident_create",
  "inventory_inbound",
  "inventory_outbound",
] as const;
export type FormId = (typeof FORM_IDS)[number];

export const FORM_FIELDS = [
  "email",
  "password",
  "name",
  "phone",
  "address",
  "invitation_code",
  "new_password",
  "confirm_password",
  "current_password",
  "contact_email",
  "country",
  "currency",
  "categories",
  "rate_per_shipment",
  "status",
  "zone",
  "notes",
  "title",
  "description",
  "category",
  "origin",
  "branch",
  "sku_id",
  "quantity",
  "reference",
  "exit_type",
  "tracking_number",
  "form_level",
] as const;
export type FormField = (typeof FORM_FIELDS)[number];

export type TelemetryWarehouse = "los_angeles" | "zaragoza";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";

/** Propiedades de cada evento del frontend (todas obligatorias; `null` donde el contrato lo admite). */
export interface FrontendEventProperties {
  navigation_section_viewed: {
    section: Section;
    previous_section: Section | null;
    navigation_trigger: "initial_load" | "in_app_navigation" | "browser_history";
  };
  form_started: { form_id: FormId; section: Section };
  form_submitted: {
    form_id: FormId;
    outcome: "success" | "validation_error" | "business_rejection" | "unauthorized" | "network_error" | "server_error";
    http_status: number | null;
    attempt_number: number;
    duration_ms: number | null;
  };
  form_abandoned: {
    form_id: FormId;
    duration_ms: number;
    fields_touched_count: number;
    last_field: FormField;
    had_failed_submit: boolean;
  };
  form_validation_failed: { form_id: FormId; failed_fields: FormField[]; attempt_number: number };
  frontend_error_captured: {
    error_kind: "uncaught_exception" | "unhandled_rejection" | "render_error" | "chunk_load_error";
    error_name: string;
    boundary: "panel" | "root" | "global" | "none";
    section: Section;
    fingerprint: string;
    digest: string | null;
    app_version: string;
    occurrence_count: number;
  };
  backend_request_failed: {
    failure_kind:
      | "network_error"
      | "timeout"
      | "api_not_configured"
      | "unreadable_response"
      | "unexpected_response_shape";
    api_route: string;
    http_method: HttpMethod;
    section: Section;
    occurrence_count: number;
  };
  page_performance_measured: {
    section: Section;
    lcp_ms: number | null;
    cls: number | null;
    inp_ms: number | null;
    ttfb_ms: number | null;
    navigation_type: "navigate" | "reload" | "back_forward" | "soft_navigation";
    device_class: "mobile" | "tablet" | "desktop";
    app_version: string;
  };
  order_history_filtered: {
    warehouse: TelemetryWarehouse | null;
    product_id: string | null;
    result_count: number | null;
  };
  session_ended: {
    end_reason: "user_logout" | "token_expired" | "unauthorized_response" | "ended_in_other_tab";
    session_duration_seconds: number | null;
  };
  telemetry_events_dropped: {
    component: "frontend_emitter";
    drop_reason: "schema_validation_failed" | "buffer_overflow" | "rate_limited" | "delivery_failed";
    affected_event_type: string;
    dropped_count: number;
    window_seconds: number;
  };
}

export type FrontendEventType = keyof FrontendEventProperties;

interface EventSpec {
  schemaVersion: string;
  /** Claves de `properties`, todas obligatorias (allowlist cerrada). */
  properties: readonly string[];
  /** `sessionId` no puede ser nulo (solo tiene sentido con sesión iniciada). */
  requiresSession: boolean;
  /** El evento lleva `requestId` (si no, siempre `null`). */
  hasRequestId: boolean;
}

export const ALLOWLIST: Record<FrontendEventType, EventSpec> = {
  navigation_section_viewed: {
    schemaVersion: "1.0.0",
    properties: ["section", "previous_section", "navigation_trigger"],
    requiresSession: false,
    hasRequestId: false,
  },
  form_started: { schemaVersion: "1.0.0", properties: ["form_id", "section"], requiresSession: false, hasRequestId: false },
  form_submitted: {
    schemaVersion: "1.0.0",
    properties: ["form_id", "outcome", "http_status", "attempt_number", "duration_ms"],
    requiresSession: false,
    hasRequestId: true,
  },
  form_abandoned: {
    schemaVersion: "1.0.0",
    properties: ["form_id", "duration_ms", "fields_touched_count", "last_field", "had_failed_submit"],
    requiresSession: false,
    hasRequestId: false,
  },
  form_validation_failed: {
    schemaVersion: "1.0.0",
    properties: ["form_id", "failed_fields", "attempt_number"],
    requiresSession: false,
    hasRequestId: false,
  },
  frontend_error_captured: {
    schemaVersion: "1.0.0",
    properties: [
      "error_kind",
      "error_name",
      "boundary",
      "section",
      "fingerprint",
      "digest",
      "app_version",
      "occurrence_count",
    ],
    requiresSession: false,
    hasRequestId: false,
  },
  backend_request_failed: {
    schemaVersion: "1.0.0",
    properties: ["failure_kind", "api_route", "http_method", "section", "occurrence_count"],
    requiresSession: false,
    hasRequestId: false,
  },
  page_performance_measured: {
    schemaVersion: "1.0.0",
    properties: ["section", "lcp_ms", "cls", "inp_ms", "ttfb_ms", "navigation_type", "device_class", "app_version"],
    requiresSession: false,
    hasRequestId: false,
  },
  order_history_filtered: {
    schemaVersion: "1.0.0",
    properties: ["warehouse", "product_id", "result_count"],
    requiresSession: true,
    hasRequestId: false,
  },
  session_ended: {
    schemaVersion: "1.0.0",
    properties: ["end_reason", "session_duration_seconds"],
    requiresSession: true,
    hasRequestId: false,
  },
  telemetry_events_dropped: {
    schemaVersion: "1.0.0",
    properties: ["component", "drop_reason", "affected_event_type", "dropped_count", "window_seconds"],
    requiresSession: false,
    hasRequestId: false,
  },
};

export function isFrontendEventType(value: string): value is FrontendEventType {
  return Object.prototype.hasOwnProperty.call(ALLOWLIST, value);
}

/**
 * Versión desplegada del backoffice (`app_version`): el hash corto del commit, como `IMAGE_TAG`, inyectado al compilar
 * con `NEXT_PUBLIC_APP_VERSION`. Sin la variable (desarrollo local), `dev`.
 */
export const APP_VERSION = /^[0-9A-Za-z._-]{1,40}$/.test(process.env.NEXT_PUBLIC_APP_VERSION ?? "")
  ? (process.env.NEXT_PUBLIC_APP_VERSION as string)
  : "dev";
