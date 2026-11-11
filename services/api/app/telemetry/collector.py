"""Colector de la telemetría: valida cada evento y guarda los válidos en `telemetry_events` (`storage`).

Dos entradas, un mismo almacenamiento:

- **Navegador** (`POST /telemetry/events`): `validate_batch` valida cada elemento del lote por separado con
  `TelemetryEvent.model_validate`; los no válidos se cuentan y se descartan sin cancelar el resto, y los válidos se
  guardan con `store_batch` (un único INSERT, de forma síncrona: la respuesta dice cuántos se han guardado).
- **Backend** (`emitter.emit` → `ingest`, canal `backend`): eventos ya validados por el emisor. Se guardan en un hilo
  aparte (`run_in_background`) para que una orden de inventario o un login no esperen a la base de la telemetría ni
  fallen si está caída (§15 del plan).

Cada lote deja una línea de log estructurada (JSON) en `trackflow.telemetry`, sin valores de los eventos:

    INFO:     trackflow.telemetry: telemetry_batch_received {"channel": "http", "received": 5, "stored": 3, ...}
"""

import json
import logging
import threading
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import get_current_user
from app.telemetry import contract
from app.telemetry.identifiers import user_ref
from app.telemetry.models import TelemetryEvent
from app.telemetry.storage import TelemetryStorageError, insert_events

logger = logging.getLogger("trackflow.telemetry")

Channel = Literal["http", "backend"]

# Por este endpoint solo entran eventos del navegador; los del backend los emite la propia API (§15).
HTTP_SOURCE = "frontend"
# Errores que se registran en el log por cada evento rechazado (solo ruta, tipo y regla; nunca el valor).
MAX_LOGGED_ERRORS = 5
# Eventos del backend pendientes de guardar como máximo: si la base no responde, no se acumulan sin límite.
MAX_PENDING_BACKEND_WRITES = 1000


@dataclass
class BatchValidation:
    """Resultado de validar un lote del navegador elemento a elemento."""

    valid: list[TelemetryEvent] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)


def _rejection(index: int, raw: Any, reason: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Motivo de un rechazo para el log: posición, `event_type` si es del catálogo y errores sin valores."""
    event_type = raw.get("event_type") if isinstance(raw, dict) else None
    return {
        "index": index,
        "event_type": event_type if event_type in contract.event_types() else None,
        "reason": reason,
        "errors": errors[:MAX_LOGGED_ERRORS],
    }


def validate_batch(raw_events: Sequence[Any], user: str | None) -> BatchValidation:
    """Valida cada elemento por separado con `TelemetryEvent.model_validate`. Un elemento no válido no para el resto.

    A los válidos se les pone el `userId` del token (`user`): lo que envíe el navegador se ignora (§8.3).
    """
    result = BatchValidation()
    for index, raw in enumerate(raw_events):
        try:
            event = TelemetryEvent.model_validate(raw)
        except ValidationError as error:
            details = error.errors(include_url=False, include_context=False, include_input=False)
            errors = [{"loc": list(item["loc"]), "type": item["type"], "msg": item["msg"]} for item in details]
            result.rejections.append(_rejection(index, raw, "schema_validation_failed", errors))
            continue
        if event.source != HTTP_SOURCE:
            result.rejections.append(_rejection(index, raw, "source_not_allowed", []))
            continue
        result.valid.append(event.model_copy(update={"user_id": user}))
    return result


def store_batch(events: Sequence[TelemetryEvent]) -> int:
    """Guarda los eventos válidos con un único INSERT (ninguno si la lista está vacía). Devuelve las filas nuevas.

    Si la base falla, registra el tipo de error (sin valores ni credenciales) y vuelve a lanzar
    `TelemetryStorageError`: no se ha guardado ningún evento del lote.
    """
    if not events:
        return 0
    try:
        return insert_events(events)
    except TelemetryStorageError as error:
        logger.error(
            "telemetry_batch_store_failed %s",
            json.dumps({"count": len(events), "error": str(error)}, ensure_ascii=False),
        )
        raise


def log_batch(channel: Channel, received: int, stored: Sequence[TelemetryEvent], inserted: int, rejections) -> None:
    """Resumen del lote: cuántos se han recibido, guardado y rechazado, y por qué (sin valores)."""
    summary = {
        "channel": channel,
        "received": received,
        "stored": len(stored),
        "rejected": len(rejections),
        "duplicates": len(stored) - inserted,
        "event_types": [event.event_type for event in stored],
        "by_type": dict(Counter(event.event_type for event in stored)),
    }
    if rejections:
        summary["rejections"] = list(rejections)
    logger.info("telemetry_batch_received %s", json.dumps(summary, ensure_ascii=False))


# --- Canal del backend ------------------------------------------------------------------------------------------

_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telemetry-writer")
_pending = threading.BoundedSemaphore(MAX_PENDING_BACKEND_WRITES)


def run_in_background(job: Callable[[], None]) -> None:
    """Ejecuta `job` en el hilo de escritura de la telemetría. Los tests la sustituyen por una llamada directa."""
    _writer.submit(job)


def ingest(events: Sequence[TelemetryEvent], channel: Channel) -> int:
    """Entrega eventos ya validados del backend: los registra en el log y los guarda en segundo plano.

    Nunca espera a la base: si hay demasiados pendientes (base caída o lenta), descarta el lote con un aviso
    `telemetry_event_dropped`. Devuelve el número de eventos entregados.
    """
    events = list(events)
    if not _pending.acquire(blocking=False):
        logger.warning(
            "telemetry_event_dropped %s",
            json.dumps(
                {"drop_reason": "storage_queue_full", "event_types": [event.event_type for event in events]},
                ensure_ascii=False,
            ),
        )
        return 0

    def job() -> None:
        try:
            inserted = store_batch(events)
            log_batch(channel, len(events), events, inserted, [])
        except TelemetryStorageError:
            pass  # ya registrado en `store_batch`
        except Exception:  # noqa: BLE001 — la telemetría nunca rompe la operación
            logger.exception("Error inesperado al guardar eventos de telemetría del backend")
        finally:
            _pending.release()

    try:
        run_in_background(job)
    except Exception:  # noqa: BLE001 — p. ej. el intérprete se está cerrando
        _pending.release()
        logger.exception("No se pudo programar el guardado de eventos de telemetría del backend")
        return 0
    return len(events)


def user_ref_from_authorization(authorization: str | None) -> str | None:
    """Seudónimo del usuario de un `Authorization: Bearer …` válido, o `None` (sin token, caducado o no válido).

    El navegador nunca calcula `userId` (§8.3): lo pone el receptor a partir del token, así nadie puede atribuir un
    evento a otra persona. Un token no válido no rechaza el lote: los eventos de páginas públicas y el `session_ended`
    de una sesión caducada también se reciben, con `userId` nulo.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        user = get_current_user(token.strip())
    except HTTPException:
        return None
    return user_ref(user.id)
