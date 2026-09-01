import Link from "next/link";
import { StageBadge } from "@/components/StageBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/domain";
import type { CandidateListItem } from "@/types/api";

export function CandidateCard({ candidate }: { candidate: CandidateListItem }) {
  return (
    <Link
      href={`/candidates/${candidate.id}`}
      className="block rounded-2xl border border-slate-200 bg-white p-5 shadow-lg shadow-slate-900/5 transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-xl"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-lg font-bold text-slate-900">{candidate.full_name}</h3>
          <p className="text-sm text-slate-600">{candidate.position}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={candidate.status} />
          <StageBadge stage={candidate.stage} />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-500">
        <span>{candidate.email}</span>
        <span>Aplicó el {formatDate(candidate.applied_at)}</span>
        <span>
          {candidate.notes_count} {candidate.notes_count === 1 ? "nota" : "notas"}
        </span>
      </div>
    </Link>
  );
}
