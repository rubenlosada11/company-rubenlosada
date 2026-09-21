/**
 * Contenido del sitio público. Fuente: CONTEXT.es.md y CONTEXT-trackflow.es.md (raíz del monorepo).
 * No añadir datos que no estén respaldados por esos documentos (clientes, logos, cifras, premios…).
 */

export const SITE = {
  name: "TrackFlow",
  url: "https://trackflow.com",
  title: "TrackFlow | Logística para e-commerce en Estados Unidos y España",
  description:
    "TrackFlow ofrece gestión de almacenes, entregas de última milla y logística inversa para marcas de e-commerce en Estados Unidos y España.",
  // Formulario de captación ya existente en uis/landing/formulario (URL pública documentada en uis/landing/README.md).
  leadFormUrl: "https://landingtrackflow.rubenlosada.com/formulario/application.html",
  linkedinUrl: "https://linkedin.com/company/trackflow",
  email: "comercial@trackflow.com",
  foundingYear: 2009,
} as const;

export const NAV_ITEMS = [
  { label: "Inicio", href: "#inicio" },
  { label: "Servicios", href: "#servicios" },
  { label: "Cobertura", href: "#cobertura" },
  { label: "Contacto", href: "#contacto" },
] as const;

export const HERO = {
  eyebrow: "Logística para e-commerce · EE. UU. + España",
  title: "Logística que escala con tu e-commerce",
  subtitle:
    "Gestión de almacenes, entregas de última milla y logística inversa en Estados Unidos y España. Más de 15 años ayudando a marcas de moda, electrónica y cosmética a crecer sin preocuparse por la operación.",
  primaryCta: "Solicitar información",
  secondaryCta: "Ver servicios",
  imageAlt:
    "Equipo de TrackFlow y robots de transporte moviendo cajas dentro de un almacén de distribución",
} as const;

export interface Fact {
  value: string;
  label: string;
}

export const FACTS: readonly Fact[] = [
  { value: "2009", label: "Año de fundación" },
  { value: "+130", label: "Profesionales" },
  { value: "2", label: "Almacenes: Los Ángeles y Zaragoza" },
  { value: "8", label: "Transportistas en ambos países" },
];

export const VALUE_PROPOSITION = {
  eyebrow: "Nuestra propuesta",
  title: "Tú vendes. Nosotros lo hacemos llegar.",
  paragraphs: [
    "Las marcas de e-commerce son buenas haciendo y vendiendo productos, pero no haciendo llegar esos productos a la puerta del cliente. Eso es lo que hacemos en TrackFlow.",
    "Desde el momento en que se hace un pedido hasta que se entrega o se devuelve, toda la operación logística es responsabilidad de TrackFlow.",
  ],
} as const;

export type IconName =
  | "warehouse"
  | "truck"
  | "return"
  | "pin"
  | "users"
  | "chip"
  | "bag"
  | "box"
  | "mail"
  | "phone"
  | "check"
  | "linkedin";

export interface Service {
  id: string;
  icon: IconName;
  title: string;
  points: readonly string[];
}

export const SERVICES: readonly Service[] = [
  {
    id: "almacenes",
    icon: "warehouse",
    title: "Gestión de Almacenes",
    points: [
      "Almacenamiento, picking y packing",
      "Inventario en tiempo real",
      "Operamos almacenes en Los Ángeles y Zaragoza",
    ],
  },
  {
    id: "ultima-milla",
    icon: "truck",
    title: "Entregas de Última Milla",
    points: [
      "Red de carriers certificados en ambos países",
      "Seguimiento unificado de envíos",
      "Gestión de incidencias y devoluciones",
    ],
  },
  {
    id: "logistica-inversa",
    icon: "return",
    title: "Logística Inversa",
    points: [
      "Gestión completa de devoluciones",
      "Inspección y reacondicionamiento",
      "Integración con tu plataforma de ventas",
    ],
  },
];

export interface ProcessStep {
  title: string;
  description: string;
}

export const PROCESS = {
  eyebrow: "Cómo trabajamos",
  title: "Del pedido a la puerta de tu cliente, y de vuelta si hace falta",
  steps: [
    {
      title: "Almacenamos tu inventario",
      description: "Tu producto se guarda en nuestros almacenes de Los Ángeles y Zaragoza.",
    },
    {
      title: "Preparamos y empaquetamos",
      description: "Cada pedido se recoge de la estantería y se empaqueta para su envío.",
    },
    {
      title: "Enviamos con nuestra red",
      description: "Entregamos a través de una red de transportistas en ambos países.",
    },
    {
      title: "Gestionamos las devoluciones",
      description: "Cuando un producto regresa, nos encargamos también de ese camino de vuelta.",
    },
  ] satisfies readonly ProcessStep[],
} as const;

export interface CoverageRegion {
  id: string;
  country: string;
  points: readonly string[];
  carriers: readonly string[];
}

export const COVERAGE = {
  eyebrow: "Cobertura",
  title: "Una operación, dos mercados",
  regions: [
    {
      id: "us",
      country: "Estados Unidos",
      points: ["Almacén en Los Ángeles", "Cobertura nacional"],
      carriers: ["UPS", "FedEx", "DHL"],
    },
    {
      id: "es",
      country: "España",
      points: ["Almacén en Zaragoza", "Cobertura peninsular e islas"],
      carriers: ["MRW", "SEUR", "DHL"],
    },
  ] satisfies readonly CoverageRegion[],
} as const;

export interface Benefit {
  icon: IconName;
  title: string;
  description: string;
}

export const BENEFITS = {
  eyebrow: "Por qué TrackFlow",
  title: "Un operador logístico pensado para marcas de e-commerce",
  items: [
    {
      icon: "pin",
      title: "Operación binacional",
      description: "Infraestructura propia en Estados Unidos y España: un solo operador para tus dos mercados.",
    },
    {
      icon: "users",
      title: "+130 profesionales",
      description: "Un equipo dedicado a tu logística.",
    },
    {
      icon: "chip",
      title: "Tecnología propia",
      description: "Para visibilidad total de tu inventario.",
    },
    {
      icon: "bag",
      title: "Especialización e-commerce",
      description: "En moda, electrónica y cosmética.",
    },
  ] satisfies readonly Benefit[],
} as const;

export const AUDIENCE = {
  eyebrow: "Para quién",
  title: "Marcas de e-commerce que quieren externalizar su logística",
  description:
    "Trabajamos con marcas medianas que venden en línea y prefieren centrarse en su producto y en sus clientes.",
  segments: ["Moda", "Electrónica", "Cosmética"],
  notes: [
    "Este sitio está pensado para empresas de e-commerce, no para consumidores finales.",
    "Para volúmenes menores a 100 envíos mensuales, nuestros servicios podrían no ser la solución más eficiente.",
  ],
} as const;

export interface Office {
  id: string;
  city: string;
  country: string;
  phone: string;
  phoneHref: string;
}

export const CONTACT = {
  eyebrow: "Contacto",
  title: "Hablemos de tu operación logística",
  description:
    "Cuéntanos qué necesitas a través del formulario de solicitud o escríbenos directamente.",
  offices: [
    {
      id: "us",
      city: "Los Ángeles",
      country: "Estados Unidos",
      phone: "+1 213 555 0147",
      phoneHref: "tel:+12135550147",
    },
    {
      id: "es",
      city: "Zaragoza",
      country: "España",
      phone: "+34 976 123 456",
      phoneHref: "tel:+34976123456",
    },
  ] satisfies readonly Office[],
} as const;

/** Marcado Schema.org exigido por el briefing del Hito 1 (CONTEXT-trackflow.es.md). */
export const ORGANIZATION_SCHEMA = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "TrackFlow",
  description: "Gestión de almacenes y entregas de última milla para e-commerce",
  url: SITE.url,
  foundingDate: String(SITE.foundingYear),
  address: [
    {
      "@type": "PostalAddress",
      addressCountry: "US",
      addressLocality: "Los Ángeles",
      addressRegion: "California",
    },
    {
      "@type": "PostalAddress",
      addressCountry: "ES",
      addressLocality: "Zaragoza",
      addressRegion: "Aragón",
    },
  ],
  contactPoint: {
    "@type": "ContactPoint",
    telephone: "+1-213-555-0147",
    contactType: "sales",
    availableLanguage: ["Spanish", "English"],
  },
  sameAs: [SITE.linkedinUrl],
  areaServed: [
    { "@type": "Country", name: "Estados Unidos" },
    { "@type": "Country", name: "Spain" },
  ],
} as const;
