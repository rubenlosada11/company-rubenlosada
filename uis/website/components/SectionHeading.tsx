interface SectionHeadingProps {
  id: string;
  eyebrow: string;
  title: string;
  description?: string;
}

export function SectionHeading({ id, eyebrow, title, description }: SectionHeadingProps) {
  return (
    <div>
      <p className="mb-4 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">{eyebrow}</p>
      <h2
        id={id}
        className="max-w-[26ch] font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl md:text-5xl"
      >
        {title}
      </h2>
      {description ? <p className="mt-4 max-w-2xl text-slate-600 md:text-lg">{description}</p> : null}
    </div>
  );
}
