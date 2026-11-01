import { Badge } from "@/components/Badge";
import { STOCK_LEVEL_LABELS, stockLevel, type StockLevel } from "@/lib/inventory";

/** Color y texto: el nivel nunca se transmite solo con el color. Umbrales en `STOCK_THRESHOLDS` (`lib/inventory.ts`). */
const TONES: Record<StockLevel, "red" | "amber" | "emerald"> = {
  out: "red",
  critical: "red",
  low: "amber",
  healthy: "emerald",
};

export function StockBadge({ stock }: { stock: number }) {
  const level = stockLevel(stock);
  return (
    <span data-stock-level={level}>
      <Badge tone={TONES[level]}>{STOCK_LEVEL_LABELS[level]}</Badge>
    </span>
  );
}
