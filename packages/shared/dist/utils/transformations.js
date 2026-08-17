/** Groups items by a derived key. Pure: does not mutate `items`. */
export function groupBy(items, keyFn) {
    const groups = {};
    for (const item of items) {
        const key = keyFn(item);
        if (!groups[key])
            groups[key] = [];
        groups[key].push(item);
    }
    return groups;
}
export function countBy(items, keyFn) {
    const counts = {};
    for (const item of items) {
        const key = keyFn(item);
        counts[key] = (counts[key] ?? 0) + 1;
    }
    return counts;
}
export function sum(items, valueFn) {
    return items.reduce((total, item) => total + valueFn(item), 0);
}
export function average(items, valueFn) {
    if (items.length === 0)
        return 0;
    return sum(items, valueFn) / items.length;
}
export function maxBy(items, valueFn) {
    if (items.length === 0)
        return undefined;
    return items.reduce((best, item) => (valueFn(item) > valueFn(best) ? item : best));
}
export function minBy(items, valueFn) {
    if (items.length === 0)
        return undefined;
    return items.reduce((best, item) => (valueFn(item) < valueFn(best) ? item : best));
}
/** Number of shipments handled per carrier name. */
export function shipmentCountByCarrier(shipments, carriers) {
    const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
    return countBy(shipments, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);
}
/** Average cost per kg per carrier, computed from real shipment cost/weight, not the carrier's list price. */
export function averageCostPerKgByCarrier(shipments, carriers) {
    const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
    const byCarrier = groupBy(shipments, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);
    const result = {};
    for (const [carrierName, carrierShipments] of Object.entries(byCarrier)) {
        const totalWeight = sum(carrierShipments, (s) => s.weightKg);
        const totalCost = sum(carrierShipments, (s) => s.costEur);
        result[carrierName] = totalWeight > 0 ? totalCost / totalWeight : 0;
    }
    return result;
}
/** On-time delivery rate per carrier, based on delivered shipments that had an estimate. */
export function onTimeDeliveryRateByCarrier(shipments, carriers) {
    const carrierNameById = new Map(carriers.map((carrier) => [carrier.id, carrier.name]));
    const delivered = shipments.filter((s) => s.status === "delivered" && s.deliveredAt !== undefined && s.estimatedDeliveryAt !== undefined);
    const byCarrier = groupBy(delivered, (shipment) => carrierNameById.get(shipment.carrierId) ?? shipment.carrierId);
    const result = {};
    for (const [carrierName, carrierShipments] of Object.entries(byCarrier)) {
        const onTimeCount = carrierShipments.filter((s) => s.deliveredAt <= s.estimatedDeliveryAt).length;
        result[carrierName] = onTimeCount / carrierShipments.length;
    }
    return result;
}
export function returnCountByReason(returns) {
    return countBy(returns, (item) => item.reason);
}
/** Share of shipments that resulted in a return request, from 0 to 1. */
export function returnRate(shipments, returns) {
    if (shipments.length === 0)
        return 0;
    return returns.length / shipments.length;
}
/** Clients whose contract expires within `thresholdDays` of `referenceDate` (default 90, per CONTEXT.es.md). */
export function clientsNearContractRenewal(clients, referenceDate, thresholdDays = 90) {
    const referenceTime = referenceDate.getTime();
    const thresholdMs = thresholdDays * 24 * 60 * 60 * 1000;
    return clients.filter((client) => {
        const endTime = new Date(client.contractEndDate).getTime();
        const daysUntilEnd = endTime - referenceTime;
        return daysUntilEnd >= 0 && daysUntilEnd <= thresholdMs;
    });
}
