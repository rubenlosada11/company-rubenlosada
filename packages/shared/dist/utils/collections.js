function compareValues(a, b) {
    if (typeof a === "number" && typeof b === "number")
        return a - b;
    if (typeof a === "string" && typeof b === "string")
        return a.localeCompare(b);
    if (typeof a === "boolean" && typeof b === "boolean")
        return Number(a) - Number(b);
    return 0;
}
/** Immutable sort by a single field. Does not mutate the input array. */
export function sortBy(items, key, direction = "asc") {
    const factor = direction === "asc" ? 1 : -1;
    return [...items].sort((a, b) => factor * compareValues(a[key], b[key]));
}
/** Immutable sort by several fields in priority order. */
export function sortByMultiple(items, criteria) {
    return [...items].sort((a, b) => {
        for (const { key, direction } of criteria) {
            const factor = direction === "asc" ? 1 : -1;
            const result = factor * compareValues(a[key], b[key]);
            if (result !== 0)
                return result;
        }
        return 0;
    });
}
/** Filters shipments by any combination of criteria (all provided criteria must match). */
export function filterShipments(shipments, criteria) {
    return shipments.filter((shipment) => {
        if (criteria.status !== undefined && shipment.status !== criteria.status)
            return false;
        if (criteria.carrierId !== undefined && shipment.carrierId !== criteria.carrierId)
            return false;
        if (criteria.originWarehouse !== undefined && shipment.originWarehouse !== criteria.originWarehouse)
            return false;
        if (criteria.destinationCountry !== undefined && shipment.destinationCountry !== criteria.destinationCountry)
            return false;
        if (criteria.clientId !== undefined && shipment.clientId !== criteria.clientId)
            return false;
        if (criteria.minWeightKg !== undefined && shipment.weightKg < criteria.minWeightKg)
            return false;
        if (criteria.maxWeightKg !== undefined && shipment.weightKg > criteria.maxWeightKg)
            return false;
        if (criteria.createdFrom !== undefined && (shipment.createdAt ?? "") < criteria.createdFrom)
            return false;
        if (criteria.createdTo !== undefined && (shipment.createdAt ?? "") > criteria.createdTo)
            return false;
        return true;
    });
}
export function filterReturns(returns, criteria) {
    return returns.filter((item) => {
        if (criteria.status !== undefined && item.status !== criteria.status)
            return false;
        if (criteria.reason !== undefined && item.reason !== criteria.reason)
            return false;
        if (criteria.clientId !== undefined && item.clientId !== criteria.clientId)
            return false;
        return true;
    });
}
export function filterClients(clients, criteria) {
    return clients.filter((client) => {
        if (criteria.country !== undefined && client.country !== criteria.country)
            return false;
        if (criteria.productType !== undefined && client.productType !== criteria.productType)
            return false;
        if (criteria.minMonthlyShipmentVolume !== undefined &&
            client.monthlyShipmentVolume < criteria.minMonthlyShipmentVolume) {
            return false;
        }
        return true;
    });
}
