/**
 * Traducciones que la telemetría necesita para no enviar nunca una URL (plan §9.4 y §14.4):
 *
 * - `sectionFor`: ruta del backoffice → `section` del catálogo. Se ignoran la query y el fragmento (la URL de
 *   `/reset-password` lleva el token de recuperación).
 * - `apiRouteTemplate`: ruta de una llamada a la API → plantilla de FastAPI (`/inventory/products/{sku_id}`), sin ids
 *   ni query. `unmatched` si no corresponde a ninguna ruta conocida.
 */
import type { Section } from "@/lib/telemetryCatalog";

const SECTION_BY_PATH: Record<string, Section> = {
  "/": "dashboard",
  "/proveedores": "suppliers",
  "/incidencias": "incident_analysis",
  "/gestor-incidencias": "incident_manager",
  "/gestor-incidencias/nueva": "incident_create",
  "/inventory": "inventory_products", // redirige a /inventory/products
  "/inventory/products": "inventory_products",
  "/inventory/orders": "inventory_orders",
  "/inventory/orders/inbound": "inventory_inbound",
  "/inventory/orders/outbound": "inventory_outbound",
  "/account/profile": "account_profile",
  "/account/change-password": "account_change_password",
  "/login": "login",
  "/register": "register",
  "/forgot-password": "forgot_password",
  "/reset-password": "reset_password",
};

/** Sección de una ruta (`pathname`, o una URL de la que solo se usa la ruta). */
export function sectionFor(pathname: string | null | undefined): Section {
  const path = (pathname ?? "/").split(/[?#]/)[0].replace(/\/+$/, "") || "/";
  return SECTION_BY_PATH[path] ?? "not_found";
}

/** Plantillas de `services/api` que usa el backoffice (las de `app.openapi()`). */
const API_ROUTES = [
  "/api/incidents",
  "/api/incidents/analyze",
  "/api/incidents/results/export",
  "/api/incidents/summary",
  "/api/incidents/{incident_id}",
  "/api/incidents/{incident_id}/status",
  "/auth/change-password",
  "/auth/forgot-password",
  "/auth/login",
  "/auth/me",
  "/auth/reset-password",
  "/auth/token",
  "/health",
  "/inventory/orders",
  "/inventory/orders/inbound",
  "/inventory/orders/outbound",
  "/inventory/products",
  "/inventory/products/{sku_id}",
  "/profiles/me",
  "/suppliers",
  "/suppliers/{supplier_id}",
  "/suppliers/{supplier_id}/rate",
  "/suppliers/{supplier_id}/status",
  "/telemetry/report",
  "/users",
  "/users/{user_id}",
].map((template) => ({ template, parts: template.split("/") }));

export function apiRouteTemplate(path: string): string {
  const parts = path.split(/[?#]/)[0].replace(/\/+$/, "").split("/");
  // Primero las rutas fijas: `/api/incidents/summary` no es `/api/incidents/{incident_id}`.
  const candidates = API_ROUTES.filter((route) => route.parts.length === parts.length);
  const exact = candidates.find((route) => route.parts.every((part, i) => part === parts[i]));
  if (exact) return exact.template;
  const withParams = candidates.find((route) =>
    route.parts.every((part, i) => part === parts[i] || (part.startsWith("{") && parts[i] !== ""))
  );
  return withParams?.template ?? "unmatched";
}
