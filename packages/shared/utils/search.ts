import type { Shipment } from "../types/models.js";

/**
 * Linear search: works on arrays in any order. Scans every element until
 * the predicate matches. O(n).
 */
export function linearSearch<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let i = 0; i < items.length; i++) {
    if (predicate(items[i])) return i;
  }
  return -1;
}

export function linearSearchShipmentByTrackingNumber(shipments: Shipment[], trackingNumber: string): number {
  return linearSearch(shipments, (shipment) => shipment.trackingNumber === trackingNumber);
}

type Primitive = string | number;

function comparePrimitive(a: Primitive, b: Primitive): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

/**
 * Binary search: requires `items` to already be sorted ascending by `key`
 * (e.g. via `sortBy(items, key, "asc")`). Repeatedly halves the search
 * range instead of scanning every element. O(log n).
 *
 * Precondition: `items` must be sorted ascending by the same `key` used
 * here, or the result is undefined.
 */
export function binarySearchBy<T, K extends keyof T>(
  sortedItems: T[],
  key: K,
  target: T[K] & Primitive
): number {
  let low = 0;
  let high = sortedItems.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const midValue = sortedItems[mid][key] as unknown as Primitive;
    const comparison = comparePrimitive(midValue, target);

    if (comparison === 0) return mid;
    if (comparison < 0) low = mid + 1;
    else high = mid - 1;
  }

  return -1;
}

/** Convenience wrapper: array must already be sorted ascending by trackingNumber. */
export function binarySearchShipmentByTrackingNumber(sortedShipments: Shipment[], trackingNumber: string): number {
  return binarySearchBy(sortedShipments, "trackingNumber", trackingNumber);
}
