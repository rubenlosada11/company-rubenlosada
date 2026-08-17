import type { Carrier, Client, ReturnRequest, Shipment } from "../types/models.js";
/**
 * Sample data grounded in CONTEXT.es.md: TrackFlow's 8 carriers (US + ES),
 * brand clients across the product categories used in the Hito 1 lead form,
 * and shipments/returns that intentionally include edge cases (invalid
 * weight, incoherent dates, an expiring contract) for manual testing.
 */
export declare const sampleCarriers: Carrier[];
export declare const sampleClients: Client[];
export declare const sampleShipments: Shipment[];
export declare const sampleReturns: ReturnRequest[];
