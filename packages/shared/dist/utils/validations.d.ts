import type { Carrier, Client, ReturnRequest, Shipment } from "../types/models.js";
export interface ValidationResult {
    valid: boolean;
    errors: string[];
}
export declare function validateShipment(shipment: Shipment): ValidationResult;
export declare function validateCarrier(carrier: Carrier): ValidationResult;
export declare function validateReturnRequest(returnRequest: ReturnRequest): ValidationResult;
export declare function validateClient(client: Client): ValidationResult;
