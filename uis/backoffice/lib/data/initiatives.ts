import type { Initiative } from "@/types";

/**
 * Fuente: CONTEXT.es.md, apartado “Qué necesitan” de cada departamento.
 * Todas son necesidades identificadas; solo se marcan como `foundation` las que ya tienen base técnica real
 * en el repo (Hito 2, packages/shared). Ninguna está implementada como producto.
 */
export const INITIATIVES: readonly Initiative[] = [
  // Operaciones de almacén
  {
    id: "wh-inventory-api",
    areaId: "warehouse",
    title: "API de inventario unificada",
    detail: "Stock en tiempo real de cualquier SKU en cualquiera de los dos almacenes.",
    status: "identified",
  },
  {
    id: "wh-order-ingestion",
    areaId: "warehouse",
    title: "Pipeline de ingesta de pedidos",
    detail: "Parseo automático de los pedidos que llegan por email.",
    status: "identified",
  },
  {
    id: "wh-dashboard",
    areaId: "warehouse",
    title: "Dashboard de operaciones de almacén",
    detail: "Visión operativa de los dos almacenes.",
    status: "identified",
  },
  {
    id: "wh-low-stock",
    areaId: "warehouse",
    title: "Alertas de stock bajo",
    detail: "Notificación al cliente y al equipo de compras.",
    status: "identified",
  },

  // Última milla y transportistas
  {
    id: "lm-carrier-engine",
    areaId: "last-mile",
    title: "Motor de selección de transportista",
    detail: "Recomienda la opción óptima según destino, peso y urgencia.",
    status: "identified",
  },
  {
    id: "lm-tracking",
    areaId: "last-mile",
    title: "Endpoint unificado de tracking",
    detail: "Agrega el estado del envío desde cualquier transportista.",
    status: "identified",
  },
  {
    id: "lm-public-portal",
    areaId: "last-mile",
    title: "Portal de seguimiento público",
    detail: "Para que el destinatario consulte su envío.",
    status: "identified",
  },
  {
    id: "lm-carrier-dashboard",
    areaId: "last-mile",
    title: "Dashboard de rendimiento de transportistas",
    detail: "Tasa de entrega a tiempo, incidencias por ruta y coste por kg.",
    status: "foundation",
    foundation:
      "Hito 2 (packages/shared): onTimeDeliveryRateByCarrier y averageCostPerKgByCarrier. Falta datos reales y la interfaz.",
  },

  // Logística inversa
  {
    id: "rl-auto-approval",
    areaId: "reverse-logistics",
    title: "Motor de aprobación automática de devoluciones",
    detail: "Reglas configurables por cliente.",
    status: "identified",
  },
  {
    id: "rl-pickup-flow",
    areaId: "reverse-logistics",
    title: "Flujo automatizado de recogida",
    detail: "Aprobación → etiqueta → instrucciones al cliente → programación con el transportista.",
    status: "identified",
  },
  {
    id: "rl-ai-inspection",
    areaId: "reverse-logistics",
    title: "Inspección asistida por IA",
    detail: "El operario fotografía el producto y la IA clasifica su estado.",
    status: "identified",
  },
  {
    id: "rl-dashboard",
    areaId: "reverse-logistics",
    title: "Dashboard de devoluciones",
    detail: "Análisis de patrones: qué se devuelve más y por qué.",
    status: "foundation",
    foundation:
      "Hito 2 (packages/shared): returnCountByReason y returnRate. Falta datos reales y la interfaz.",
  },

  // Experiencia del cliente
  {
    id: "cx-first-line-agent",
    areaId: "customer-experience",
    title: "Agente de CX de primera línea",
    detail: "Resuelve consultas de seguimiento y estado de devoluciones.",
    status: "identified",
  },
  {
    id: "cx-knowledge-base",
    areaId: "customer-experience",
    title: "Base de conocimiento semántica (RAG)",
    detail: "Indexada para búsqueda semántica sobre políticas logísticas.",
    status: "identified",
  },
  {
    id: "cx-tickets",
    areaId: "customer-experience",
    title: "Sistema unificado de tickets",
    detail: "Email, WhatsApp y teléfono en un solo sitio.",
    status: "identified",
  },
  {
    id: "cx-dashboard",
    areaId: "customer-experience",
    title: "Dashboard de CX en tiempo real",
    detail: "Estado de la atención al cliente.",
    status: "identified",
  },
  {
    id: "cx-sentiment",
    areaId: "customer-experience",
    title: "Análisis de sentimiento",
    detail: "Detectar clientes frustrados antes de que escalen.",
    status: "identified",
  },
  {
    id: "cx-multilanguage",
    areaId: "customer-experience",
    title: "Soporte multiidioma (español + inglés)",
    detail: "Opcional pero muy recomendado; empezar por un idioma base.",
    status: "identified",
    optional: true,
  },

  // Comercial y relación con clientes
  {
    id: "co-crm",
    areaId: "commercial",
    title: "Integración con CRM",
    detail: "Perfil unificado de cliente.",
    status: "identified",
  },
  {
    id: "co-client-reports",
    areaId: "commercial",
    title: "Informes PDF automáticos para clientes",
    detail: "Generados por un agente en lugar de consolidarse a mano cada mes.",
    status: "identified",
  },
  {
    id: "co-health-dashboard",
    areaId: "commercial",
    title: "Dashboard de salud de cliente",
    detail: "Puntuación de riesgo de renovación.",
    status: "identified",
  },
  {
    id: "co-renewal-alerts",
    areaId: "commercial",
    title: "Alertas de vencimiento de contrato",
    detail: "Avisos a 90 y a 30 días del vencimiento.",
    status: "foundation",
    foundation:
      "Hito 2 (packages/shared): clientsNearContractRenewal con umbral configurable (90 días por defecto). Falta el envío de alertas.",
  },
  {
    id: "co-sales-agent",
    areaId: "commercial",
    title: "Agente comercial",
    detail: "Sugiere el servicio y la estructura de precios más relevantes para cada prospecto.",
    status: "identified",
  },

  // Tecnología
  {
    id: "te-telemetry",
    areaId: "technology",
    title: "Telemetría y logging centralizados",
    detail: "De ambos países.",
    status: "identified",
  },
  {
    id: "te-data-pipeline",
    areaId: "technology",
    title: "Pipeline de datos",
    detail: "Alimenta todos los dashboards de la empresa.",
    status: "identified",
  },
  {
    id: "te-monitoring",
    areaId: "technology",
    title: "Monitorización en tiempo real",
    detail: "Con alertas automáticas.",
    status: "identified",
  },
  {
    id: "te-docs-agent",
    areaId: "technology",
    title: "Agente de documentación técnica",
    detail: "Documentar integraciones y sistemas hoy sin documentar.",
    status: "identified",
  },
  {
    id: "te-ops-automation",
    areaId: "technology",
    title: "Automatización de tareas de operaciones",
    detail: "Backups, health checks y notificaciones de incidencias con contexto.",
    status: "identified",
  },

  // Dirección ejecutiva
  {
    id: "ex-dashboard",
    areaId: "executive",
    title: "Dashboard ejecutivo global",
    detail:
      "KPIs de ambas operaciones: volumen de envíos, entrega a tiempo, coste operativo, devoluciones y satisfacción del cliente.",
    status: "identified",
  },
  {
    id: "ex-weekly-report",
    areaId: "executive",
    title: "Informe semanal automático",
    detail: "Generado los lunes a las 7:00.",
    status: "identified",
  },
  {
    id: "ex-country-compare",
    areaId: "executive",
    title: "Comparativas por país",
    detail: "Estados Unidos frente a España.",
    status: "identified",
  },
  {
    id: "ex-threshold-alerts",
    areaId: "executive",
    title: "Alertas por umbrales",
    detail: "Avisos cuando un KPI cruza un límite.",
    status: "identified",
  },
  {
    id: "ex-ai-assistant",
    areaId: "executive",
    title: "Asistente de IA en lenguaje natural",
    detail: "Al que el CEO puede consultar el negocio en lenguaje natural.",
    status: "identified",
  },
];
