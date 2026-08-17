import type {
  Client,
  CountryCode,
  ProductType,
  ReturnReason,
  ReturnRequest,
  ReturnStatus,
  Shipment,
  ShipmentStatus,
  WarehouseLocation,
} from "../types/models.js";

export type SortDirection = "asc" | "desc";

export interface SortCriterion<T> {
  key: keyof T;
  direction: SortDirection;
}

function compareValues(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "string" && typeof b === "string") return a.localeCompare(b);
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return 0;
}

/** Immutable sort by a single field. Does not mutate the input array. */
export function sortBy<T>(items: T[], key: keyof T, direction: SortDirection = "asc"): T[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...items].sort((a, b) => factor * compareValues(a[key], b[key]));
}

/** Immutable sort by several fields in priority order. */
export function sortByMultiple<T>(items: T[], criteria: SortCriterion<T>[]): T[] {
  return [...items].sort((a, b) => {
    for (const { key, direction } of criteria) {
      const factor = direction === "asc" ? 1 : -1;
      const result = factor * compareValues(a[key], b[key]);
      if (result !== 0) return result;
    }
    return 0;
  });
}

export interface ShipmentFilterCriteria {
  status?: ShipmentStatus;
  carrierId?: string;
  originWarehouse?: WarehouseLocation;
  destinationCountry?: CountryCode;
  clientId?: string;
  minWeightKg?: number;
  maxWeightKg?: number;
  createdFrom?: string;
  createdTo?: string;
}

/** Filters shipments by any combination of criteria (all provided criteria must match). */
export function filterShipments(shipments: Shipment[], criteria: ShipmentFilterCriteria): Shipment[] {
  return shipments.filter((shipment) => {
    if (criteria.status !== undefined && shipment.status !== criteria.status) return false;
    if (criteria.carrierId !== undefined && shipment.carrierId !== criteria.carrierId) return false;
    if (criteria.originWarehouse !== undefined && shipment.originWarehouse !== criteria.originWarehouse) return false;
    if (criteria.destinationCountry !== undefined && shipment.destinationCountry !== criteria.destinationCountry) return false;
    if (criteria.clientId !== undefined && shipment.clientId !== criteria.clientId) return false;
    if (criteria.minWeightKg !== undefined && shipment.weightKg < criteria.minWeightKg) return false;
    if (criteria.maxWeightKg !== undefined && shipment.weightKg > criteria.maxWeightKg) return false;
    if (criteria.createdFrom !== undefined && (shipment.createdAt ?? "") < criteria.createdFrom) return false;
    if (criteria.createdTo !== undefined && (shipment.createdAt ?? "") > criteria.createdTo) return false;
    return true;
  });
}

export interface ReturnFilterCriteria {
  status?: ReturnStatus;
  reason?: ReturnReason;
  clientId?: string;
}

export function filterReturns(returns: ReturnRequest[], criteria: ReturnFilterCriteria): ReturnRequest[] {
  return returns.filter((item) => {
    if (criteria.status !== undefined && item.status !== criteria.status) return false;
    if (criteria.reason !== undefined && item.reason !== criteria.reason) return false;
    if (criteria.clientId !== undefined && item.clientId !== criteria.clientId) return false;
    return true;
  });
}

export interface ClientFilterCriteria {
  country?: CountryCode;
  productType?: ProductType;
  minMonthlyShipmentVolume?: number;
}

export function filterClients(clients: Client[], criteria: ClientFilterCriteria): Client[] {
  return clients.filter((client) => {
    if (criteria.country !== undefined && client.country !== criteria.country) return false;
    if (criteria.productType !== undefined && client.productType !== criteria.productType) return false;
    if (
      criteria.minMonthlyShipmentVolume !== undefined &&
      client.monthlyShipmentVolume < criteria.minMonthlyShipmentVolume
    ) {
      return false;
    }
    return true;
  });
}
