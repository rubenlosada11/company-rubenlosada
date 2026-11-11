"""Telemetría: receptor de eventos (`POST /telemetry/events`) y reporte técnico (`GET /telemetry/report`).

`GET /telemetry/report` (autenticado): métricas operacionales de `telemetry_events` en el periodo pedido. El endpoint
solo resuelve el periodo y devuelve el reporte de `app/telemetry/report.py` (caché de 60 s); las métricas las calcula
`app/telemetry/analysis.py` con SQL + Pandas. Documentación: `docs/telemetry/telemetry-report.md`.

`POST /telemetry/events` valida cada evento y guarda los válidos.

Recibe lotes `{"events": [...]}` del `TelemetryService` del backoffice (misma URL, método y envelope que en la fase de
captura) y responde `200 {"received": n, "stored": s, "rejected": r}`, con `received = stored + rejected`.

- **Validación parcial**: el envelope se comprueba a mano y cada elemento de `events` se valida por separado con
  `TelemetryEvent.model_validate` (`collector.validate_batch`). Un evento no válido se cuenta en `rejected` y no
  cancela el lote. Solo se aceptan eventos con `source = frontend` (lo del navegador no es de fiar, §15).
- **Un único INSERT** con todos los válidos (`collector.store_batch`), en una transacción; ninguno si no hay válidos.
- **Errores del envelope** (cuerpo vacío o que no es JSON, sin `events`, `events` que no es una lista o con más de 50
  elementos, claves de más): 422 con el formato del resto de la API, sin tocar la base. 413 si supera 64 KB.
- **Fallo de la base**: 503 sin cifras (el navegador reintenta el lote con 5xx). Nunca un 200 si no se ha guardado.
- Público: un token no válido o ausente no rechaza el lote (`userId` queda nulo).
- El cuerpo se lee como JSON aunque llegue como `text/plain`: `navigator.sendBeacon` lo envía así para que el navegador
  no tenga que hacer una petición previa de CORS (que un *beacon* no puede hacer).
"""

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError

from app.dependencies import get_current_user
from app.telemetry.analysis import TelemetryAnalysisError
from app.telemetry.collector import log_batch, store_batch, user_ref_from_authorization, validate_batch
from app.telemetry.models import MAX_BATCH_BYTES, MAX_BATCH_EVENTS, TelemetryBatch, TelemetryBatchResult
from app.telemetry.report import PeriodError, TelemetryReport, get_report, resolve_period
from app.telemetry.storage import TelemetryStorageError

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

BODY_TOO_LARGE = f"El lote supera el tamaño máximo ({MAX_BATCH_BYTES // 1024} KB)."
STORAGE_UNAVAILABLE = "No se han podido guardar los eventos de telemetría. Inténtalo de nuevo más tarde."
REPORT_UNAVAILABLE = "No se ha podido calcular el reporte de telemetría. Inténtalo de nuevo más tarde."


def _envelope_error(error_type: str, loc: tuple[Any, ...], msg: str) -> RequestValidationError:
    return RequestValidationError([{"type": error_type, "loc": ("body", *loc), "msg": msg}])


def parse_envelope(body: bytes) -> list[Any]:
    """Elementos de `{"events": [...]}`, todavía sin validar. 422 si el envelope no tiene esa forma."""
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise _envelope_error("json_invalid", (), "El cuerpo no es un JSON válido.") from None
    if not isinstance(payload, dict):
        raise _envelope_error("model_attributes_type", (), 'El cuerpo debe ser un objeto {"events": [...]}.')
    extra = sorted(key for key in payload if key != "events")
    if extra:
        raise _envelope_error("extra_forbidden", (extra[0],), "Clave no permitida en el envelope.")
    if "events" not in payload:
        raise _envelope_error("missing", ("events",), "Falta el campo events.")
    events = payload["events"]
    if not isinstance(events, list):
        raise _envelope_error("list_type", ("events",), "events debe ser una lista.")
    if len(events) > MAX_BATCH_EVENTS:
        raise _envelope_error("too_long", ("events",), f"El lote admite como máximo {MAX_BATCH_EVENTS} eventos.")
    return events


@router.post(
    "/events",
    response_model=TelemetryBatchResult,
    summary="Recibe un lote de eventos de telemetría del backoffice y guarda los válidos",
    description=(
        f"Lote de hasta {MAX_BATCH_EVENTS} eventos del catálogo de `docs/telemetry/event-schemas.json` (envelope "
        "estándar). Valida cada evento por separado, pone `userId` desde el token Bearer (opcional) y guarda los "
        "válidos en `telemetry_events` con un único INSERT. Los no válidos se cuentan en `rejected` sin rechazar el "
        "lote."
    ),
    responses={
        413: {"description": "Cuerpo de más de 64 KB"},
        422: {"description": "Envelope mal formado (no es JSON, falta `events`, no es una lista o tiene más de 50)"},
        503: {"description": "No se han podido guardar los eventos (no se ha guardado ninguno del lote)"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": TelemetryBatch.model_json_schema(by_alias=True)}},
        }
    },
)
async def receive_events(request: Request) -> TelemetryBatchResult:
    body = await request.body()
    if len(body) > MAX_BATCH_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=BODY_TOO_LARGE)
    raw_events = parse_envelope(body)

    # Lo que envíe el navegador en `userId` se ignora: lo decide el token (TinyDB, de ahí el hilo aparte).
    user = await run_in_threadpool(user_ref_from_authorization, request.headers.get("authorization"))
    batch = validate_batch(raw_events, user)
    try:
        inserted = await run_in_threadpool(store_batch, batch.valid)
    except TelemetryStorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORAGE_UNAVAILABLE) from None

    log_batch("http", len(raw_events), batch.valid, inserted, batch.rejections)
    return TelemetryBatchResult(received=len(raw_events), stored=len(batch.valid), rejected=len(batch.rejections))


@router.get(
    "/report",
    response_model=TelemetryReport,
    dependencies=[Depends(get_current_user)],
    summary="Reporte técnico de la telemetría: volumen, incidencias, autenticación y envíos fallidos",
    description=(
        "Métricas operacionales de `telemetry_events` en el periodo `[from, to)` (UTC, inicio inclusivo y fin "
        "exclusivo). Sin fechas: los últimos 7 días hasta el minuto siguiente al actual. Solo `start_date`: hasta "
        "ahora. Solo `end_date`: los 7 días anteriores. Fechas ISO 8601; sin zona horaria se interpretan como UTC. "
        "Máximo 366 días. El resultado se guarda 60 s en una caché en memoria por periodo."
    ),
    responses={
        401: {"description": "Sin token o token no válido"},
        422: {"description": "Fecha no válida, inicio no anterior al fin o periodo de más de 366 días"},
        503: {"description": "No se han podido leer los eventos (no se cachea nada)"},
    },
)
def telemetry_report(
    start_date: Annotated[datetime | None, Query(description="Inicio del periodo (ISO 8601, inclusivo).")] = None,
    end_date: Annotated[datetime | None, Query(description="Fin del periodo (ISO 8601, exclusivo).")] = None,
) -> TelemetryReport:
    try:
        start, end = resolve_period(start_date, end_date)
    except PeriodError as error:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("query", error.field), "msg": str(error)}]
        ) from None
    try:
        return get_report(start, end)
    except TelemetryAnalysisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REPORT_UNAVAILABLE) from None
