"""Receptor temporal (*stub*) de la telemetría: valida y registra, **sin guardar nada**.

Todo evento aceptado, venga del navegador (`POST /telemetry/events`) o del emisor del backend, pasa por `ingest`, que
deja una línea de log estructurada (JSON) en `trackflow.telemetry`:

    INFO:     trackflow.telemetry: telemetry_batch_received {"channel": "http", "count": 2, "event_types": [...]}

No escribe en Supabase, en SQLite ni en TinyDB, ni guarda los eventos en memoria. Cuando exista el almacenamiento,
`ingest` es el único punto que hay que cambiar (y `TELEMETRY_ENDPOINT` dirá a dónde reenviar).
"""

import json
import logging
from collections import Counter
from collections.abc import Sequence
from typing import Literal

from fastapi import HTTPException

from app.dependencies import get_current_user
from app.telemetry.identifiers import user_ref
from app.telemetry.models import TelemetryEvent

logger = logging.getLogger("trackflow.telemetry")

Channel = Literal["http", "backend"]


def ingest(events: Sequence[TelemetryEvent], channel: Channel) -> int:
    """Registra un lote ya validado: cuántos eventos y el `event_type` de cada uno (en orden). Devuelve el número."""
    summary = {
        "channel": channel,
        "count": len(events),
        "event_types": [event.event_type for event in events],
        "by_type": dict(Counter(event.event_type for event in events)),
    }
    logger.info("telemetry_batch_received %s", json.dumps(summary, ensure_ascii=False))
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
