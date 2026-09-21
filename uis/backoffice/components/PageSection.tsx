interface PageSectionProps {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function PageSection({ id, title, description, children }: PageSectionProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-40 lg:scroll-mt-24">
      <div className="mb-5">
        <h2 id={`${id}-title`} className="font-heading text-2xl tracking-tight text-slate-900">
          {title}
        </h2>
        {description ? <p className="mt-1.5 max-w-3xl text-sm text-slate-600">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
