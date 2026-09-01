import { STATUS_BADGE_CLASSES, statusLabel } from "@/lib/domain";
import type { CandidateStatus } from "@/types/api";

export function StatusBadge({ status }: { status: CandidateStatus | string }) {
  const classes = STATUS_BADGE_CLASSES[status as CandidateStatus] ?? "bg-slate-100 text-slate-700 border-slate-300";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-bold ${classes}`}
    >
      {statusLabel(status)}
    </span>
  );
}
