import { sampleCarriers, sampleClients, sampleReturns, sampleShipments } from "./data/sample-data.js";
import { filterClients, filterReturns, filterShipments, sortBy } from "./utils/collections.js";
import { binarySearchBy, binarySearchShipmentByTrackingNumber, linearSearch, linearSearchShipmentByTrackingNumber, } from "./utils/search.js";
import { averageCostPerKgByCarrier, clientsNearContractRenewal, onTimeDeliveryRateByCarrier, returnCountByReason, returnRate, shipmentCountByCarrier, } from "./utils/transformations.js";
import { validateCarrier, validateClient, validateReturnRequest, validateShipment } from "./utils/validations.js";
function section(title) {
    console.log(`\n=== ${title} ===`);
}
section("Filtrado");
console.log("Envíos entregados en España:", filterShipments(sampleShipments, { status: "delivered", destinationCountry: "ES" }).map((s) => s.trackingNumber));
console.log("Devoluciones pendientes de revisión:", filterReturns(sampleReturns, { status: "pending_review" }).map((r) => r.id));
console.log("Clientes de moda o electrónica en EE. UU.:", filterClients(sampleClients, { country: "US" }).map((c) => c.companyName));
console.log("Caso límite — filtrar array vacío:", filterShipments([], { status: "delivered" }));
section("Ordenamiento");
console.log("Envíos por peso ascendente:", sortBy(sampleShipments, "weightKg", "asc").map((s) => `${s.trackingNumber} (${s.weightKg}kg)`));
console.log("Envíos por coste descendente:", sortBy(sampleShipments, "costEur", "desc")
    .slice(0, 3)
    .map((s) => `${s.trackingNumber} (${s.costEur}€)`));
section("Búsqueda lineal");
console.log("Buscar TF-ES-00003 (existe):", linearSearchShipmentByTrackingNumber(sampleShipments, "TF-ES-00003"));
console.log("Buscar TF-ZZ-00000 (no existe):", linearSearchShipmentByTrackingNumber(sampleShipments, "TF-ZZ-00000"));
console.log("Caso límite — búsqueda lineal en array vacío:", linearSearch([], () => true));
section("Búsqueda binaria (precondición: array ordenado por trackingNumber)");
const sortedByTracking = sortBy(sampleShipments, "trackingNumber", "asc");
console.log("Buscar TF-US-00005 (existe):", binarySearchShipmentByTrackingNumber(sortedByTracking, "TF-US-00005"));
console.log("Buscar TF-US-99999 (no existe):", binarySearchShipmentByTrackingNumber(sortedByTracking, "TF-US-99999"));
console.log("Caso límite — búsqueda binaria en array vacío:", binarySearchBy([], "trackingNumber", "TF-US-00001"));
console.log("Caso límite — array de un solo elemento:", binarySearchBy(sortedByTracking.slice(0, 1), "trackingNumber", sortedByTracking[0].trackingNumber));
section("Agregaciones");
console.log("Envíos por transportista:", shipmentCountByCarrier(sampleShipments, sampleCarriers));
console.log("Coste medio por kg y transportista:", averageCostPerKgByCarrier(sampleShipments, sampleCarriers));
console.log("Tasa de entrega a tiempo por transportista:", onTimeDeliveryRateByCarrier(sampleShipments, sampleCarriers));
console.log("Devoluciones por motivo:", returnCountByReason(sampleReturns));
console.log("Tasa de devoluciones:", `${(returnRate(sampleShipments, sampleReturns) * 100).toFixed(1)}%`);
console.log("Clientes con contrato a renovar en 90 días (referencia 2026-08-17):", clientsNearContractRenewal(sampleClients, new Date("2026-08-17"), 90).map((c) => c.companyName));
section("Validaciones");
for (const shipment of sampleShipments) {
    const result = validateShipment(shipment);
    if (!result.valid)
        console.log(`Envío inválido [${shipment.id}]:`, result.errors);
}
for (const returnRequest of sampleReturns) {
    const result = validateReturnRequest(returnRequest);
    if (!result.valid)
        console.log(`Devolución inválida [${returnRequest.id}]:`, result.errors);
}
for (const client of sampleClients) {
    const result = validateClient(client);
    if (!result.valid)
        console.log(`Cliente inválido [${client.id}]:`, result.errors);
}
for (const carrier of sampleCarriers) {
    const result = validateCarrier(carrier);
    if (!result.valid)
        console.log(`Transportista inválido [${carrier.id}]:`, result.errors);
}
