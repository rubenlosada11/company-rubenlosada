import type { Carrier, Client, ReturnReason, ReturnRequest, Shipment } from "../types/models.js";

/** Groups items by a derived key. Pure: does not mutate `items`. */
export function groupBy<T, K extends string>(items: T[], keyFn: (item: T) => K): Record<K, T[]> {
  const groups = {} as Record<K, T[]>;
  for (const item of items) {
    const key = keyFn(item);
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

export function countBy<T, K extends string>(items: T[], keyFn: (item: T) => K): Record<K, number> {
  const counts = {} as Record<K, number>;
  for (const item of items) {
    const key = keyFn(item);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

export function sum<T>(items: T[], valueFn: (item: T) => number): number {
  return items.reduce((total, item) => total + valueFn(item), 0);
}

export function average<T>(items: T[], valueFn: (item: T) => number): number {
  if (items.length === 0) return 0;
  return sum(items, valueFn) / items.length;
}

export function maxBy<T>(items: T[], valueFn: (item: T) => number): T | undefined {
  if (items.length === 0) return undefined;
  return items.reduce((best, item) => (valueFn(item) > valueFn(best) ? item : best));
}

export function minBy<T>(items: T[], valueFn: (item: T) => number): T | undefined {
  if (items.length === 0) return undefined;
  return items.reduce((best, item) => (valueFn(item) < valueFn(best) ? item : best));
}

/** Number of shipments handled per carrier name. */
export function shipmentCountByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number> {
  const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
  return countBy(shipments, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);
}

/** Average cost per kg per carrier, computed from real shipment cost/weight, not the carrier's list price. */
export function averageCostPerKgByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number> {
  const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
  const byCarrier = groupBy(shipments, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);

  const result: Record<string, number> = {};
  for (const [carrierName, carrierShipments] of Object.entries(byCarrier)) {
    const totalWeight = sum(carrierShipments, (s) => s.weightKg);
    const totalCost = sum(carrierShipments, (s) => s.costEur);
    result[carrierName] = totalWeight > 0 ? totalCost / totalWeight : 0;
  }
  return result;
}

/** On-time delivery rate per carrier, based on delivered shipments that had an estimate. */
export function onTimeDeliveryRateByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number> {
  const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
  const delivered = shipments.filter(
    (s) => s.status === "delivered" && s.deliveredAt !== undefined && s.estimatedDeliveryAt !== undefined
  );
  const byCarrier = groupBy(delivered, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);

  const result: Record<string, number> = {};
  for (const [carrierName, carrierShipments] of Object.entries(byCarrier)) {
    const onTimeCount = carrierShipments.filter((s) => (s.deliveredAt as string) <= (s.estimatedDeliveryAt as string)).length;
    result[carrierName] = onTimeCount / carrierShipments.length;
  }
  return result;
}

export function returnCountByReason(returns: ReturnRequest[]): Record<ReturnReason, number> {
  return countBy(returns, (item) => item.reason);
}

/** Share of shipments that resulted in a return request, from 0 to 1. */
export function returnRate(shipments: Shipment[], returns: ReturnRequest[]): number {
  if (shipments.length === 0) return 0;
  return returns.length / shipments.length;
}

/** Clients whose contract expires within `thresholdDays` of `referenceDate` (default 90, per CONTEXT.es.md). */
export function clientsNearContractRenewal(
  clients: Client[],
  referenceDate: Date,
  thresholdDays = 90
): Client[] {
  const referenceTime = referenceDate.getTime();
  const thresholdMs = thresholdDays * 24 * 60 * 60 * 1000;

  return clients.filter((client) => {
    const endTime = new Date(client.contractEndDate).getTime();
    const daysUntilEnd = endTime - referenceTime;
    return daysUntilEnd >= 0 && daysUntilEnd <= thresholdMs;
  });
}
