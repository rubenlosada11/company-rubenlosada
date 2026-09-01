import { stageLabel } from "@/lib/domain";
import type { CandidateStage } from "@/types/api";

export function StageBadge({ stage }: { stage: CandidateStage | string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-bold text-slate-700">
      {stageLabel(stage)}
    </span>
  );
}
