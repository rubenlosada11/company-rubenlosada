import type { AreaId, Initiative, InitiativeStatus } from "@/types";

export type StatusFilter = InitiativeStatus | "all";
export type AreaFilter = AreaId | "all";

export const STATUS_LABELS: Record<InitiativeStatus, string> = {
  identified: "Necesidad identificada",
  foundation: "Base técnica disponible",
};

export const STATUS_ORDER: readonly InitiativeStatus[] = ["identified", "foundation"];

export interface InitiativeFilters {
  areaId: AreaFilter;
  status: StatusFilter;
}

export function filterInitiatives(
  initiatives: readonly Initiative[],
  { areaId, status }: InitiativeFilters,
): Initiative[] {
  return initiatives.filter(
    (item) => (areaId === "all" || item.areaId === areaId) && (status === "all" || item.status === status),
  );
}

export function countByArea(initiatives: readonly Initiative[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of initiatives) counts[item.areaId] = (counts[item.areaId] ?? 0) + 1;
  return counts;
}

export function countByStatus(initiatives: readonly Initiative[]): Record<InitiativeStatus, number> {
  const counts: Record<InitiativeStatus, number> = { identified: 0, foundation: 0 };
  for (const item of initiatives) counts[item.status] += 1;
  return counts;
}
