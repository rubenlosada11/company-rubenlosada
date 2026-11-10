"""Receptor temporal de telemetría del backoffice (`POST /telemetry/events`). Fase de captura.

Recibe lotes `{"events": [...]}` del `TelemetryService` del backoffice, valida cada evento contra el catálogo aprobado
(`app/telemetry/models.py`), pone `userId` a partir del token y registra el lote en el log. **No guarda nada.**

- Público: un token no válido o ausente no rechaza el lote (`userId` queda nulo).
- El cuerpo se lee como JSON aunque llegue como `text/plain`: `navigator.sendBeacon` lo envía así para que el navegador
  no tenga que hacer una petición previa de CORS (que un *beacon* no puede hacer).
- Solo acepta eventos con `source = frontend`: lo que llega del navegador no es de fiar (§15) y los eventos del backend
  no entran por aquí.
- 422 si algún evento no cumple el contrato (el lote entero se rechaza, sin repetir los valores recibidos); 413 si el
  cuerpo supera 64 KB.
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.telemetry.collector import ingest, user_ref_from_authorization
from app.telemetry.models import MAX_BATCH_BYTES, MAX_BATCH_EVENTS, TelemetryBatch, TelemetryBatchAccepted

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

ONLY_FRONTEND = "Este receptor solo acepta eventos con source 'frontend'."
BODY_TOO_LARGE = f"El lote supera el tamaño máximo ({MAX_BATCH_BYTES // 1024} KB)."


@router.post(
    "/events",
    response_model=TelemetryBatchAccepted,
    summary="Recibe un lote de eventos de telemetría del backoffice",
    description=(
        f"Lote de 1 a {MAX_BATCH_EVENTS} eventos del catálogo de `docs/telemetry/event-schemas.json` (envelope "
        "estándar). Valida, pone `userId` desde el token Bearer (opcional) y registra el lote en el log. Receptor "
        "temporal: no guarda los eventos."
    ),
    responses={
        413: {"description": "Cuerpo de más de 64 KB"},
        422: {"description": "Algún evento no cumple el contrato (campos, formatos o allowlist de propiedades)"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": TelemetryBatch.model_json_schema(by_alias=True)}},
        }
    },
)
async def receive_events(request: Request) -> TelemetryBatchAccepted:
    body = await request.body()
    if len(body) > MAX_BATCH_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=BODY_TOO_LARGE)
    try:
        batch = TelemetryBatch.model_validate_json(body)
    except ValidationError as error:
        errors = error.errors(include_url=False)
        raise RequestValidationError([{**item, "loc": ("body", *item["loc"])} for item in errors]) from None

    foreign = [
        {"type": "value_error", "loc": ("body", "events", index, "source"), "msg": ONLY_FRONTEND}
        for index, event in enumerate(batch.events)
        if event.source != "frontend"
    ]
    if foreign:
        raise RequestValidationError(foreign)

    # Lo que envíe el navegador en `userId` se ignora: lo decide el token (TinyDB, de ahí el hilo aparte).
    user = await run_in_threadpool(user_ref_from_authorization, request.headers.get("authorization"))
    events = [event.model_copy(update={"user_id": user}) for event in batch.events]
    return TelemetryBatchAccepted(received=ingest(events, channel="http"))
