"""Eventos de origen del reporte semanal (BRIEFING de pipelines §3) y forma de la extracción."""

INBOUND = "inbound_order_created"
OUTBOUND = "outbound_order_created"
STOCKOUT = "stock_threshold_triggered"
DISCREPANCY = "inventory_discrepancy_detected"

# Los cuatro eventos del BRIEFING. Ninguno más («resiste la tentación de ampliar el alcance»).
SOURCE_EVENT_TYPES = (INBOUND, OUTBOUND, STOCKOUT, DISCREPANCY)

# Columnas de `telemetry_events` que necesita el cálculo (y nada más: ni `user_id` ni `session_id`).
COLUMNS = ["id", "event_type", "timestamp", "tags"]
