import { filterShipments, sortBy } from "../../packages/shared/dist/utils/collections.js";
import { binarySearchShipmentByTrackingNumber, linearSearchShipmentByTrackingNumber, } from "../../packages/shared/dist/utils/search.js";
import { averageCostPerKgByCarrier, clientsNearContractRenewal, onTimeDeliveryRateByCarrier, returnCountByReason, returnRate, shipmentCountByCarrier, } from "../../packages/shared/dist/utils/transformations.js";
import { validateCarrier, validateClient, validateReturnRequest, validateShipment, } from "../../packages/shared/dist/utils/validations.js";
import { sampleCarriers, sampleClients, sampleReturns, sampleShipments } from "../../packages/shared/dist/data/sample-data.js";
const carrierNameById = new Map(sampleCarriers.map((carrier) => [carrier.id, carrier.name]));
function byId(id) {
    const el = document.getElementById(id);
    if (!el)
        throw new Error(`No se encontró el elemento #${id}`);
    return el;
}
function renderTable(containerId, columns, rows) {
    const container = byId(containerId);
    if (rows.length === 0) {
        container.innerHTML = '<p class="text-sm text-slate-500 italic">Sin resultados.</p>';
        return;
    }
    const head = `<tr>${columns.map((c) => `<th class="px-3 py-2 text-left font-semibold text-slate-600 border-b border-slate-200">${c}</th>`).join("")}</tr>`;
    const body = rows
        .map((row) => `<tr class="odd:bg-slate-50">${row.map((cell) => `<td class="px-3 py-1.5 border-b border-slate-100 text-slate-800">${cell}</td>`).join("")}</tr>`)
        .join("");
    container.innerHTML = `<table class="w-full text-sm"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}
function shipmentRow(shipment) {
    return [
        shipment.trackingNumber || "(vacío)",
        carrierNameById.get(shipment.carrierId) ?? shipment.carrierId,
        shipment.originWarehouse,
        shipment.destinationCountry,
        shipment.weightKg,
        shipment.costEur,
        shipment.status,
        shipment.createdAt ?? "",
    ];
}
const SHIPMENT_COLUMNS = ["Tracking", "Transportista", "Almacén", "País", "Peso (kg)", "Coste (€)", "Estado", "Creado"];
// ---- Datos de ejemplo ----
function renderSampleData() {
    renderTable("sample-shipments", SHIPMENT_COLUMNS, sampleShipments.map(shipmentRow));
    renderTable("sample-carriers", ["Nombre", "País", "€/kg", "Tasa a tiempo"], sampleCarriers.map((c) => [c.name, c.country, c.costPerKgEur, `${Math.round(c.onTimeDeliveryRate * 100)}%`]));
    renderTable("sample-clients", ["Empresa", "País", "Tipo producto", "Volumen/mes", "Fin de contrato"], sampleClients.map((c) => [c.companyName, c.country, c.productType, c.monthlyShipmentVolume, c.contractEndDate]));
    renderTable("sample-returns", ["Id", "Envío", "Cliente", "Motivo", "Estado", "Solicitada", "Resuelta"], sampleReturns.map((r) => [r.id, r.shipmentId, r.clientId, r.reason, r.status, r.requestedAt, r.resolvedAt ?? ""]));
}
// ---- Filtrado ----
function runFilter() {
    const statusValue = byId("filter-status").value;
    const carrierValue = byId("filter-carrier").value;
    const countryValue = byId("filter-country").value;
    const minWeightValue = byId("filter-min-weight").value;
    const maxWeightValue = byId("filter-max-weight").value;
    const criteria = {};
    if (statusValue)
        criteria.status = statusValue;
    if (carrierValue)
        criteria.carrierId = carrierValue;
    if (countryValue)
        criteria.destinationCountry = countryValue;
    if (minWeightValue)
        criteria.minWeightKg = Number(minWeightValue);
    if (maxWeightValue)
        criteria.maxWeightKg = Number(maxWeightValue);
    const results = filterShipments(sampleShipments, criteria);
    byId("filter-count").textContent = `${results.length} envío(s) encontrados`;
    renderTable("filter-results", SHIPMENT_COLUMNS, results.map(shipmentRow));
}
// ---- Ordenamiento ----
function runSort() {
    const field = byId("sort-field").value;
    const direction = byId("sort-direction").value;
    const sorted = sortBy(sampleShipments, field, direction);
    renderTable("sort-results", SHIPMENT_COLUMNS, sorted.map(shipmentRow));
}
// ---- Búsqueda lineal ----
function runLinearSearch() {
    const tracking = byId("linear-search-input").value.trim();
    const index = linearSearchShipmentByTrackingNumber(sampleShipments, tracking);
    const output = byId("linear-search-result");
    if (sampleShipments.length === 0) {
        output.textContent = "El array de envíos está vacío.";
    }
    else if (index === -1) {
        output.textContent = `No se encontró ningún envío con tracking "${tracking}".`;
    }
    else {
        output.textContent = `Encontrado en el índice ${index}: ${sampleShipments[index].trackingNumber} (${sampleShipments[index].status}).`;
    }
}
// ---- Búsqueda binaria ----
function runBinarySearch() {
    const tracking = byId("binary-search-input").value.trim();
    const sorted = sortBy(sampleShipments, "trackingNumber", "asc");
    renderTable("binary-search-sorted", SHIPMENT_COLUMNS, sorted.map(shipmentRow));
    const index = binarySearchShipmentByTrackingNumber(sorted, tracking);
    const output = byId("binary-search-result");
    if (sorted.length === 0) {
        output.textContent = "El array de envíos está vacío.";
    }
    else if (index === -1) {
        output.textContent = `No se encontró ningún envío con tracking "${tracking}" en el array ordenado.`;
    }
    else {
        output.textContent = `Encontrado en el índice ${index}: ${sorted[index].trackingNumber} (${sorted[index].status}).`;
    }
}
// ---- Agregaciones ----
function runAggregations() {
    renderKeyValue("agg-count-by-carrier", shipmentCountByCarrier(sampleShipments, sampleCarriers));
    renderKeyValue("agg-cost-per-kg", averageCostPerKgByCarrier(sampleShipments, sampleCarriers), (v) => `${v.toFixed(2)} €/kg`);
    renderKeyValue("agg-on-time-rate", onTimeDeliveryRateByCarrier(sampleShipments, sampleCarriers), (v) => `${Math.round(v * 100)}%`);
    renderKeyValue("agg-returns-by-reason", returnCountByReason(sampleReturns));
    const rate = returnRate(sampleShipments, sampleReturns);
    byId("agg-return-rate").textContent = `Tasa de devoluciones: ${(rate * 100).toFixed(1)}%`;
    const nearRenewal = clientsNearContractRenewal(sampleClients, new Date(), 90);
    const nearRenewalOutput = byId("agg-near-renewal");
    nearRenewalOutput.textContent =
        nearRenewal.length === 0
            ? "Ningún cliente con contrato a renovar en los próximos 90 días."
            : nearRenewal.map((c) => `${c.companyName} (vence ${c.contractEndDate})`).join(", ");
}
function renderKeyValue(containerId, data, format = String) {
    const container = byId(containerId);
    const entries = Object.entries(data);
    if (entries.length === 0) {
        container.innerHTML = '<p class="text-sm text-slate-500 italic">Sin datos.</p>';
        return;
    }
    container.innerHTML = `<ul class="text-sm space-y-1">${entries
        .map(([key, value]) => `<li><span class="font-medium">${key}:</span> ${format(value)}</li>`)
        .join("")}</ul>`;
}
// ---- Validaciones ----
function formatValidation(label, result) {
    if (result.valid)
        return "";
    return `<li class="mb-1"><span class="font-medium text-rose-700">${label}</span><ul class="list-disc pl-5 text-rose-600">${result.errors
        .map((e) => `<li>${e}</li>`)
        .join("")}</ul></li>`;
}
function runValidateSampleData() {
    const items = [];
    for (const shipment of sampleShipments)
        items.push(formatValidation(`Envío ${shipment.id}`, validateShipment(shipment)));
    for (const returnRequest of sampleReturns)
        items.push(formatValidation(`Devolución ${returnRequest.id}`, validateReturnRequest(returnRequest)));
    for (const client of sampleClients)
        items.push(formatValidation(`Cliente ${client.id}`, validateClient(client)));
    for (const carrier of sampleCarriers)
        items.push(formatValidation(`Transportista ${carrier.id}`, validateCarrier(carrier)));
    const errorsFound = items.filter(Boolean);
    const output = byId("validation-results");
    output.innerHTML =
        errorsFound.length === 0
            ? '<p class="text-sm text-emerald-700">Todos los datos de ejemplo son válidos.</p>'
            : `<ul>${errorsFound.join("")}</ul>`;
}
function runValidateCustomShipment() {
    const shipment = {
        id: "custom",
        trackingNumber: byId("custom-tracking").value.trim(),
        clientId: sampleClients[0]?.id ?? "",
        carrierId: sampleCarriers[0]?.id ?? "",
        originWarehouse: byId("custom-warehouse").value,
        destinationCountry: byId("custom-country").value,
        weightKg: Number(byId("custom-weight").value),
        costEur: Number(byId("custom-cost").value),
        status: byId("custom-status").value,
        createdAt: "2026-08-17",
    };
    const result = validateShipment(shipment);
    const output = byId("custom-validation-result");
    output.innerHTML = result.valid
        ? '<p class="text-sm text-emerald-700">✓ Envío válido.</p>'
        : `<ul class="list-disc pl-5 text-sm text-rose-600">${result.errors.map((e) => `<li>${e}</li>`).join("")}</ul>`;
}
function populateSelectOptions() {
    const carrierSelect = byId("filter-carrier");
    for (const carrier of sampleCarriers) {
        const option = document.createElement("option");
        option.value = carrier.id;
        option.textContent = carrier.name;
        carrierSelect.appendChild(option);
    }
}
function init() {
    populateSelectOptions();
    renderSampleData();
    byId("filter-run").addEventListener("click", runFilter);
    byId("sort-run").addEventListener("click", runSort);
    byId("linear-search-run").addEventListener("click", runLinearSearch);
    byId("binary-search-run").addEventListener("click", runBinarySearch);
    byId("aggregations-run").addEventListener("click", runAggregations);
    byId("validation-run").addEventListener("click", runValidateSampleData);
    byId("custom-validate-run").addEventListener("click", runValidateCustomShipment);
}
init();
