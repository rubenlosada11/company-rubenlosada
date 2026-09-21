import type { BusinessArea } from "@/types";

/** Fuente: CONTEXT.es.md, secciones “Cómo está organizada la empresa” y “Los departamentos y sus problemas”. */
export const AREAS: readonly BusinessArea[] = [
  {
    id: "warehouse",
    name: "Operaciones de almacén",
    owner: "Ana Whitfield",
    role: "Responsable de operaciones de almacén",
    team: "~70 operarios + 2 responsables de almacén",
    situation:
      "Los almacenes de Los Ángeles y Zaragoza usan sistemas distintos y no comparten una visión de inventario en tiempo real. Los pedidos llegan por email en formatos distintos y se transcriben a mano, el picking se hace con listas en papel y las discrepancias de inventario se detectan tarde.",
  },
  {
    id: "last-mile",
    name: "Última milla y transportistas",
    owner: "Carlos Vega",
    role: "Coordinación de transportistas",
    team: "6 coordinadores logísticos",
    situation:
      "Se trabaja con 8 transportistas en ambos países (UPS, FedEx y DHL en EE. UU.; MRW, SEUR y DHL en España, más dos locales). La asignación es manual, el seguimiento obliga a consultar cada portal por separado y no hay datos históricos de rendimiento.",
  },
  {
    id: "reverse-logistics",
    name: "Logística inversa",
    owner: "Sofía Ramos",
    role: "Responsable de logística inversa",
    team: "5 personas",
    situation:
      "Las devoluciones son entre el 18 % y el 25 % del volumen según cliente y país. Cada una pasa por revisión manual sin criterios automáticos, la inspección del producto es subjetiva y no hay visibilidad de qué se devuelve más ni por qué.",
  },
  {
    id: "customer-experience",
    name: "Experiencia del cliente",
    owner: "Valentina Cruz",
    role: "Responsable de atención al cliente",
    team: "15 agentes (Los Ángeles y Zaragoza)",
    situation:
      "Se atiende a marcas (B2B) y a consumidores finales (B2C) por email, WhatsApp y teléfono, sin sistema unificado de tickets ni base de conocimiento. Cerca del 80 % de las consultas podría resolverse automáticamente y fuera de horario no hay cobertura.",
  },
  {
    id: "commercial",
    name: "Comercial y relación con clientes",
    owner: "Miguel Torres",
    role: "Director Comercial",
    team: "4 account managers + 4 de desarrollo de negocio",
    situation:
      "Las cuentas se gestionan en hojas de cálculo personales e hilos de email, sin CRM. Los informes mensuales a cada cliente se consolidan a mano en PDF y no hay visibilidad de qué clientes corren riesgo de no renovar.",
  },
  {
    id: "technology",
    name: "Tecnología",
    owner: "Andrés Kim",
    role: "CTO",
    team: "7 personas (Zaragoza)",
    situation:
      "Arquitectura fruto de crecimiento no planificado: dos sistemas de almacén, un ERP de principios de los 2010, scripts Python punto a punto sin documentar y bases de datos en dos proveedores cloud. No hay telemetría centralizada y desplegar una funcionalidad lleva entre una y dos semanas.",
  },
  {
    id: "executive",
    name: "Dirección ejecutiva",
    // CONTEXT.es.md nombra al CEO también como “Daniel Espinoza”; el desarrollador decidió (2026-09-22) usar
    // “Thomas Harry, fundador y CEO”. Ver memory-bank/projectbrief.md antes de cambiarlo.
    owner: "Thomas Harry",
    role: "Fundador y CEO",
    team: "Directores de área",
    situation:
      "El informe consolidado semanal lo preparan a mano los directores (3-4 horas cada uno) y llega con hasta dos días de antigüedad. No hay una visión unificada del negocio por país.",
  },
];
