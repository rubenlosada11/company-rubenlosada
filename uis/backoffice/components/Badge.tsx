type Tone = "neutral" | "amber" | "emerald" | "blue";

const TONES: Record<Tone, string> = {
  neutral: "border-slate-300 bg-white text-slate-700",
  amber: "border-amber-200 bg-amber-50 text-amber-900",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
  blue: "border-blue-200 bg-blue-50 text-blue-900",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-bold ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}
