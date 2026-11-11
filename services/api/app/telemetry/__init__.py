"""Telemetría de TrackFlow: captura y almacenamiento (plan en `docs/telemetry/telemetry-plan.md`).

- `contract`: el catálogo aprobado (`event-schemas.json`, copia exacta de `docs/telemetry/`) y su validación.
- `models`: modelos Pydantic del envelope (`TelemetryEvent`), del lote (solo para OpenAPI) y de la respuesta.
- `config`: variables de entorno (`TELEMETRY_ENDPOINT`, `TELEMETRY_PSEUDONYM_KEY`, `TELEMETRY_ENVIRONMENT`).
- `identifiers`: seudónimos (`userId`, `account_ref`) y normalización de identificadores de negocio (§8.3 y §8.4).
- `collector`: valida cada evento por separado y guarda los válidos (un INSERT por lote); el backend, en segundo plano.
- `storage`: tabla `telemetry_events` (migración `migrations/20261110120000_telemetry_events.sql`) e inserción.
- `context`: correlación por petición (`X-Request-Id`, `X-Session-Id`) y detección de ediciones directas de stock.
- `emitter`: emisor del backend (eventos de negocio que solo conoce la API, como las órdenes de inventario).

Documentación: `docs/telemetry/telemetry-capture.md` (captura) y `docs/telemetry/telemetry-storage.md` (almacenamiento).
"""
