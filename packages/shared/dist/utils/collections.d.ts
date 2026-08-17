import type { Client, CountryCode, ProductType, ReturnReason, ReturnRequest, ReturnStatus, Shipment, ShipmentStatus, WarehouseLocation } from "../types/models.js";
export type SortDirection = "asc" | "desc";
export interface SortCriterion<T> {
    key: keyof T;
    direction: SortDirection;
}
/** Immutable sort by a single field. Does not mutate the input array. */
export declare function sortBy<T>(items: T[], key: keyof T, direction?: SortDirection): T[];
/** Immutable sort by several fields in priority order. */
export declare function sortByMultiple<T>(items: T[], criteria: SortCriterion<T>[]): T[];
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
export declare function filterShipments(shipments: Shipment[], criteria: ShipmentFilterCriteria): Shipment[];
export interface ReturnFilterCriteria {
    status?: ReturnStatus;
    reason?: ReturnReason;
    clientId?: string;
}
export declare function filterReturns(returns: ReturnRequest[], criteria: ReturnFilterCriteria): ReturnRequest[];
export interface ClientFilterCriteria {
    country?: CountryCode;
    productType?: ProductType;
    minMonthlyShipmentVolume?: number;
}
export declare function filterClients(clients: Client[], criteria: ClientFilterCriteria): Client[];
