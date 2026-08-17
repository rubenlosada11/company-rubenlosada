import type { Carrier, Client, ReturnReason, ReturnRequest, Shipment } from "../types/models.js";
/** Groups items by a derived key. Pure: does not mutate `items`. */
export declare function groupBy<T, K extends string>(items: T[], keyFn: (item: T) => K): Record<K, T[]>;
export declare function countBy<T, K extends string>(items: T[], keyFn: (item: T) => K): Record<K, number>;
export declare function sum<T>(items: T[], valueFn: (item: T) => number): number;
export declare function average<T>(items: T[], valueFn: (item: T) => number): number;
export declare function maxBy<T>(items: T[], valueFn: (item: T) => number): T | undefined;
export declare function minBy<T>(items: T[], valueFn: (item: T) => number): T | undefined;
/** Number of shipments handled per carrier name. */
export declare function shipmentCountByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number>;
/** Average cost per kg per carrier, computed from real shipment cost/weight, not the carrier's list price. */
export declare function averageCostPerKgByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number>;
/** On-time delivery rate per carrier, based on delivered shipments that had an estimate. */
export declare function onTimeDeliveryRateByCarrier(shipments: Shipment[], carriers: Carrier[]): Record<string, number>;
export declare function returnCountByReason(returns: ReturnRequest[]): Record<ReturnReason, number>;
/** Share of shipments that resulted in a return request, from 0 to 1. */
export declare function returnRate(shipments: Shipment[], returns: ReturnRequest[]): number;
/** Clients whose contract expires within `thresholdDays` of `referenceDate` (default 90, per CONTEXT.es.md). */
export declare function clientsNearContractRenewal(clients: Client[], referenceDate: Date, thresholdDays?: number): Client[];
