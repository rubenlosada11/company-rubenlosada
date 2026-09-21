import type { BusinessArea } from "@/types";

interface AreaCardProps {
  area: BusinessArea;
  initiativeCount: number;
  selected: boolean;
  onToggle: () => void;
}

export function AreaCard({ area, initiativeCount, selected, onToggle }: AreaCardProps) {
  return (
    <article
      className={`flex flex-col rounded-2xl border bg-white p-5 shadow-sm transition ${
        selected ? "border-blue-600 ring-2 ring-blue-200" : "border-slate-200"
      }`}
    >
      <h3 className="font-heading text-lg text-slate-900">{area.name}</h3>
      <p className="mt-1 text-sm font-semibold text-blue-800">
        {area.owner ? `${area.owner} · ${area.role}` : area.role}
      </p>
      <p className="text-xs text-slate-500">{area.team}</p>
      <p className="mt-3 flex-1 text-sm leading-relaxed text-slate-600">{area.situation}</p>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onToggle}
        className={`mt-4 rounded-full border px-4 py-2 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${
          selected
            ? "border-blue-700 bg-blue-700 text-white hover:bg-blue-800"
            : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
        }`}
      >
        {selected ? "Mostrando sus iniciativas" : "Ver iniciativas"} ({initiativeCount})
      </button>
    </article>
  );
}
