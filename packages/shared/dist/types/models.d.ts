import type { BaseEntity } from "./index.js";
/**
 * Domain types for TrackFlow (see /CONTEXT.es.md).
 * TrackFlow operates last-mile delivery + warehousing across two countries
 * (US: Los Angeles, ES: Zaragoza) through 8 carriers, and handles returns
 * (18-25% of volume) and brand-client contracts.
 */
export type CountryCode = "US" | "ES";
export type WarehouseLocation = "Los Angeles" | "Zaragoza";
export type ShipmentStatus = "pending" | "in_transit" | "delivered" | "delayed" | "lost";
export type ReturnReason = "wrong_size" | "defective" | "not_as_described" | "changed_mind" | "other";
export type ReturnStatus = "pending_review" | "approved" | "rejected" | "refurbished" | "discarded";
export type ProductType = "moda" | "electronica" | "cosmetica" | "alimentacion" | "otro";
/** A carrier TrackFlow works with (UPS, FedEx, DHL, MRW, SEUR, etc.). */
export interface Carrier extends BaseEntity {
    name: string;
    country: CountryCode;
    costPerKgEur: number;
    /** Historical on-time delivery rate, 0 to 1. */
    onTimeDeliveryRate: number;
}
/** A brand client (e-commerce company) with an annual contract. */
export interface Client extends BaseEntity {
    companyName: string;
    country: CountryCode;
    productType: ProductType;
    monthlyShipmentVolume: number;
    contractStartDate: string;
    contractEndDate: string;
    accountManager: string;
}
/** A shipment moving from a TrackFlow warehouse to a customer. */
export interface Shipment extends BaseEntity {
    trackingNumber: string;
    clientId: string;
    carrierId: string;
    originWarehouse: WarehouseLocation;
    destinationCountry: CountryCode;
    weightKg: number;
    costEur: number;
    status: ShipmentStatus;
    /** Date the shipment was expected to arrive by. */
    estimatedDeliveryAt?: string;
    /** Date the shipment actually arrived, set once status is "delivered". */
    deliveredAt?: string;
}
/** A return request tied to a previously placed shipment. */
export interface ReturnRequest extends BaseEntity {
    shipmentId: string;
    clientId: string;
    reason: ReturnReason;
    status: ReturnStatus;
    requestedAt: string;
    resolvedAt?: string;
}
