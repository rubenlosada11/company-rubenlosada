"""Telemetría de TrackFlow: fase de **captura** (plan en `docs/telemetry/telemetry-plan.md`).

- `contract`: el catálogo aprobado (`event-schemas.json`, copia exacta de `docs/telemetry/`) y su validación.
- `models`: modelos Pydantic del envelope y del lote (`TelemetryEvent`, `TelemetryBatch`), reutilizables cuando el
  receptor pase a guardar los eventos.
- `config`: variables de entorno (`TELEMETRY_ENDPOINT`, `TELEMETRY_PSEUDONYM_KEY`, `TELEMETRY_ENVIRONMENT`).
- `identifiers`: seudónimos (`userId`, `account_ref`) y normalización de identificadores de negocio (§8.3 y §8.4).
- `collector`: receptor temporal (*stub*): valida y registra en el log; no guarda nada.
- `context`: correlación por petición (`X-Request-Id`, `X-Session-Id`) y detección de ediciones directas de stock.
- `emitter`: emisor del backend (eventos de negocio que solo conoce la API, como las órdenes de inventario).

Documentación de la implementación: `docs/telemetry/telemetry-capture.md`.
"""
