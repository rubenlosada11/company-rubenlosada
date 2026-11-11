"""Modelos Pydantic del envelope de telemetría (§8 del plan) y del lote que recibe `POST /telemetry/events`.

Los nombres de campo de Python siguen la convención del backend (`snake_case`) y los del JSON los del contrato
(`eventId`, `sessionId`, `userId`, `schemaVersion`, `requestId` en camelCase; `event_type` en snake_case): cada campo
declara su alias. `model_dump(by_alias=True)` devuelve el evento tal y como lo define el contrato; `storage.to_row` lo
convierte en una fila de `telemetry_events`.

Validación en dos capas:

1. Pydantic: campos obligatorios, tipos estrictos (sin convertir `5` en `"5"`) y ninguna clave fuera del envelope.
2. `contract.validate_event`: el esquema del `event_type` en `event-schemas.json` (formatos de `eventId`, `timestamp`,
   `sessionId`…, fuentes permitidas, nulabilidad por evento y **allowlist cerrada** de `properties`).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from app.telemetry.contract import validate_event

# Límites del canal del navegador (plan §15): lotes de hasta 50 eventos y 64 KB.
MAX_BATCH_EVENTS = 50
MAX_BATCH_BYTES = 64 * 1024

Source = Literal["frontend", "backend", "internal_process"]
Environment = Literal["development", "test", "production"]

# Los errores de un evento se resumen: con un lote mal formado no hace falta la lista completa.
MAX_REPORTED_ERRORS = 10


class TelemetryEvent(BaseModel):
    """Un evento del catálogo con su envelope estándar."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    event_id: StrictStr = Field(alias="eventId", description="UUID del evento (v4, o v5 determinista).")
    timestamp: StrictStr = Field(description="Momento del hecho, ISO 8601 en UTC con sufijo Z.")
    session_id: StrictStr | None = Field(alias="sessionId", description="Sesión autenticada del backoffice.")
    user_id: StrictStr | None = Field(alias="userId", description="Seudónimo del usuario (lo pone el receptor).")
    event_type: StrictStr = Field(description="Nombre del evento en el catálogo (`entidad_acción`).")
    schema_version: StrictStr = Field(alias="schemaVersion", description="Versión del esquema del event_type.")
    request_id: StrictStr | None = Field(alias="requestId", description="Correlación con la petición HTTP.")
    source: Source = Field(description="Componente que emite el evento.")
    environment: Environment = Field(description="Entorno de origen.")
    properties: dict[str, Any] = Field(description="Datos del evento según la allowlist de su event_type.")

    @model_validator(mode="after")
    def matches_contract(self) -> "TelemetryEvent":
        errors = validate_event(self.to_contract())
        if errors:
            hidden = len(errors) - MAX_REPORTED_ERRORS
            summary = "; ".join(errors[:MAX_REPORTED_ERRORS]) + (f"; y {hidden} más" if hidden > 0 else "")
            raise ValueError(f"el evento no cumple el contrato de telemetría: {summary}")
        return self

    def to_contract(self) -> dict[str, Any]:
        """El evento con los nombres del contrato (camelCase en el envelope)."""
        return self.model_dump(by_alias=True)


class TelemetryBatch(BaseModel):
    """Cuerpo de `POST /telemetry/events`, **solo para documentar** el endpoint en OpenAPI.

    El receptor no lo usa para validar: valida el envelope a mano y cada evento por separado con `TelemetryEvent`, para
    que un evento no válido no rechace el lote entero.
    """

    model_config = ConfigDict(extra="forbid")

    events: Annotated[list[TelemetryEvent], Field(max_length=MAX_BATCH_EVENTS)]


class TelemetryBatchResult(BaseModel):
    """Respuesta del receptor. Siempre se cumple `received = stored + rejected`."""

    received: int = Field(ge=0, description="Elementos recibidos en `events`.")
    stored: int = Field(ge=0, description="Eventos válidos guardados en `telemetry_events` (o que ya estaban).")
    rejected: int = Field(ge=0, description="Elementos que no cumplen el contrato y no se han guardado.")
