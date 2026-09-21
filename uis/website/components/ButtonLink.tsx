type Variant = "primary" | "secondary" | "inverse";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-blue-700 text-white shadow-lg shadow-blue-900/20 hover:-translate-y-0.5 hover:bg-blue-800",
  secondary:
    "border border-slate-300 bg-white/70 text-slate-800 hover:bg-white",
  inverse:
    "bg-white text-blue-900 shadow-lg shadow-blue-950/30 hover:-translate-y-0.5 hover:bg-blue-50",
};

interface ButtonLinkProps {
  href: string;
  children: React.ReactNode;
  variant?: Variant;
  external?: boolean;
  className?: string;
}

export function ButtonLink({
  href,
  children,
  variant = "primary",
  external = false,
  className = "",
}: ButtonLinkProps) {
  return (
    <a
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      className={`inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </a>
  );
}
