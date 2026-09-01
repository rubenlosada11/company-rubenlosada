"use client";

import { STAGE_LABELS, STAGE_ORDER, STATUS_LABELS, STATUS_ORDER } from "@/lib/domain";
import type { CandidateStage, CandidateStatus } from "@/types/api";

interface FiltersBarProps {
  status: CandidateStatus | "";
  stage: CandidateStage | "";
  search: string;
  onStatusChange: (status: CandidateStatus | "") => void;
  onStageChange: (stage: CandidateStage | "") => void;
  onSearchChange: (search: string) => void;
}

const selectClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto";

export function FiltersBar({
  status,
  stage,
  search,
  onStatusChange,
  onStageChange,
  onSearchChange,
}: FiltersBarProps) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white/80 p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-center">
      <div className="flex flex-col gap-1.5 sm:flex-1 sm:min-w-[220px]">
        <label htmlFor="search" className="text-xs font-bold uppercase tracking-wide text-slate-500">
          Buscar
        </label>
        <input
          id="search"
          type="search"
          placeholder="Nombre o email…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="status" className="text-xs font-bold uppercase tracking-wide text-slate-500">
          Estado
        </label>
        <select
          id="status"
          value={status}
          onChange={(e) => onStatusChange(e.target.value as CandidateStatus | "")}
          className={selectClasses}
        >
          <option value="">Todos los estados</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="stage" className="text-xs font-bold uppercase tracking-wide text-slate-500">
          Etapa
        </label>
        <select
          id="stage"
          value={stage}
          onChange={(e) => onStageChange(e.target.value as CandidateStage | "")}
          className={selectClasses}
        >
          <option value="">Todas las etapas</option>
          {STAGE_ORDER.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
