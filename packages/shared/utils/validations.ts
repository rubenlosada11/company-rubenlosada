import type {
  Carrier,
  Client,
  ReturnRequest,
  Shipment,
} from "../types/models.js";

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

const SHIPMENT_STATUSES = ["pending", "in_transit", "delivered", "delayed", "lost"] as const;
const RETURN_REASONS = ["wrong_size", "defective", "not_as_described", "changed_mind", "other"] as const;
const RETURN_STATUSES = ["pending_review", "approved", "rejected", "refurbished", "discarded"] as const;
const PRODUCT_TYPES = ["moda", "electronica", "cosmetica", "alimentacion", "otro"] as const;
const COUNTRY_CODES = ["US", "ES"] as const;

function toResult(errors: string[]): ValidationResult {
  return { valid: errors.length === 0, errors };
}

export function validateShipment(shipment: Shipment): ValidationResult {
  const errors: string[] = [];

  if (!shipment.trackingNumber || shipment.trackingNumber.trim().length === 0) {
    errors.push("El número de seguimiento (trackingNumber) es obligatorio");
  }
  if (!shipment.clientId) {
    errors.push("El envío debe estar asociado a un cliente (clientId)");
  }
  if (!shipment.carrierId) {
    errors.push("El envío debe estar asociado a un transportista (carrierId)");
  }
  if (!(shipment.weightKg > 0)) {
    errors.push("El peso (weightKg) debe ser mayor que 0");
  }
  if (shipment.costEur < 0) {
    errors.push("El coste (costEur) no puede ser negativo");
  }
  if (!SHIPMENT_STATUSES.includes(shipment.status)) {
    errors.push(`El estado (status) debe ser uno de: ${SHIPMENT_STATUSES.join(", ")}`);
  }
  if (!COUNTRY_CODES.includes(shipment.destinationCountry)) {
    errors.push(`El país de destino (destinationCountry) debe ser uno de: ${COUNTRY_CODES.join(", ")}`);
  }
  if (shipment.status === "delivered" && !shipment.deliveredAt) {
    errors.push('Un envío con status "delivered" debe tener fecha de entrega (deliveredAt)');
  }
  if (
    shipment.deliveredAt &&
    shipment.createdAt &&
    new Date(shipment.deliveredAt).getTime() < new Date(shipment.createdAt).getTime()
  ) {
    errors.push("La fecha de entrega (deliveredAt) no puede ser anterior a la de creación (createdAt)");
  }

  return toResult(errors);
}

export function validateCarrier(carrier: Carrier): ValidationResult {
  const errors: string[] = [];

  if (!carrier.name || carrier.name.trim().length === 0) {
    errors.push("El nombre del transportista es obligatorio");
  }
  if (!COUNTRY_CODES.includes(carrier.country)) {
    errors.push(`El país (country) debe ser uno de: ${COUNTRY_CODES.join(", ")}`);
  }
  if (carrier.costPerKgEur < 0) {
    errors.push("El coste por kg (costPerKgEur) no puede ser negativo");
  }
  if (carrier.onTimeDeliveryRate < 0 || carrier.onTimeDeliveryRate > 1) {
    errors.push("La tasa de entrega a tiempo (onTimeDeliveryRate) debe estar entre 0 y 1");
  }

  return toResult(errors);
}

export function validateReturnRequest(returnRequest: ReturnRequest): ValidationResult {
  const errors: string[] = [];

  if (!returnRequest.shipmentId) {
    errors.push("La devolución debe estar asociada a un envío (shipmentId)");
  }
  if (!returnRequest.clientId) {
    errors.push("La devolución debe estar asociada a un cliente (clientId)");
  }
  if (!RETURN_REASONS.includes(returnRequest.reason)) {
    errors.push(`El motivo (reason) debe ser uno de: ${RETURN_REASONS.join(", ")}`);
  }
  if (!RETURN_STATUSES.includes(returnRequest.status)) {
    errors.push(`El estado (status) debe ser uno de: ${RETURN_STATUSES.join(", ")}`);
  }
  if (!returnRequest.requestedAt) {
    errors.push("La fecha de solicitud (requestedAt) es obligatoria");
  }
  if (
    returnRequest.resolvedAt &&
    new Date(returnRequest.resolvedAt).getTime() < new Date(returnRequest.requestedAt).getTime()
  ) {
    errors.push("La fecha de resolución (resolvedAt) no puede ser anterior a la de solicitud (requestedAt)");
  }

  return toResult(errors);
}

export function validateClient(client: Client): ValidationResult {
  const errors: string[] = [];

  if (!client.companyName || client.companyName.trim().length < 2) {
    errors.push("El nombre de la empresa (companyName) debe tener al menos 2 caracteres");
  }
  if (!COUNTRY_CODES.includes(client.country)) {
    errors.push(`El país (country) debe ser uno de: ${COUNTRY_CODES.join(", ")}`);
  }
  if (!PRODUCT_TYPES.includes(client.productType)) {
    errors.push(`El tipo de producto (productType) debe ser uno de: ${PRODUCT_TYPES.join(", ")}`);
  }
  if (client.monthlyShipmentVolume < 0) {
    errors.push("El volumen mensual de envíos (monthlyShipmentVolume) no puede ser negativo");
  }
  if (!client.contractStartDate || !client.contractEndDate) {
    errors.push("Las fechas de contrato (contractStartDate y contractEndDate) son obligatorias");
  } else if (new Date(client.contractEndDate).getTime() <= new Date(client.contractStartDate).getTime()) {
    errors.push("La fecha de fin de contrato (contractEndDate) debe ser posterior a la de inicio (contractStartDate)");
  }

  return toResult(errors);
}
