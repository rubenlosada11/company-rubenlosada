import type { Shipment } from "../types/models.js";
/**
 * Linear search: works on arrays in any order. Scans every element until
 * the predicate matches. O(n).
 */
export declare function linearSearch<T>(items: T[], predicate: (item: T) => boolean): number;
export declare function linearSearchShipmentByTrackingNumber(shipments: Shipment[], trackingNumber: string): number;
type Primitive = string | number;
/**
 * Binary search: requires `items` to already be sorted ascending by `key`
 * (e.g. via `sortBy(items, key, "asc")`). Repeatedly halves the search
 * range instead of scanning every element. O(log n).
 *
 * Precondition: `items` must be sorted ascending by the same `key` used
 * here, or the result is undefined.
 */
export declare function binarySearchBy<T, K extends keyof T>(sortedItems: T[], key: K, target: T[K] & Primitive): number;
/** Convenience wrapper: array must already be sorted ascending by trackingNumber. */
export declare function binarySearchShipmentByTrackingNumber(sortedShipments: Shipment[], trackingNumber: string): number;
export {};
