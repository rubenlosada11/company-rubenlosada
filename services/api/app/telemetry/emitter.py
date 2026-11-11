"""Emisor de telemetría del backend: los eventos que solo la API puede afirmar (órdenes registradas, rechazos, login).

Cada evento se construye **campo a campo** desde valores conocidos (modelos y enums, nunca la petición entera), se
valida contra el catálogo con `TelemetryEvent` y se entrega al colector (`collector.ingest`, canal `backend`), que lo
guarda en `telemetry_events` en segundo plano, con el mismo almacenamiento que los lotes del navegador.

Garantías (plan §15): emitir **nunca lanza ni bloquea** la operación de negocio. Un evento que no cumple el contrato
(p. ej. falta `TELEMETRY_PSEUDONYM_KEY` y el evento exige `userId`) se descarta con un aviso en el log, sin valores.

- `source`: `backend` dentro de una petición HTTP; `internal_process` fuera (seeds y scripts), con `sessionId` y
  `requestId` nulos.
- `eventId`: UUID v4, salvo en los eventos que nacen de una fila (órdenes): UUID v5 determinista (§8.3), para poder
  reconstruirlos desde las tablas sin duplicarlos.
- `timestamp`: el `created_at` de la fila en las órdenes; el momento actual en el resto.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.telemetry import contract
from app.telemetry.collector import ingest, user_ref_from_authorization
from app.telemetry.config import get_environment
from app.telemetry.context import current_context
from app.telemetry.identifiers import account_ref, client_slug, user_ref, warehouse_id
from app.telemetry.models import TelemetryEvent

logger = logging.getLogger("trackflow.telemetry")

# Espacio de nombres de los UUID v5 deterministas (§8.3).
EVENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://trackflow/telemetry")

_UNSET: Any = object()


def format_timestamp(moment: datetime) -> str:
    """ISO 8601 en UTC con milisegundos y `Z`. Una fecha sin zona (SQLite) se interpreta como UTC."""
    moment = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def deterministic_event_id(*parts: object) -> str:
    """UUID v5 de `"{environment}:{parte}:{parte}…"`."""
    return str(uuid.uuid5(EVENT_NAMESPACE, ":".join([get_environment(), *map(str, parts)])))


def emit(
    event_type: str,
    properties: dict[str, Any],
    *,
    actor_id: str | None = None,
    user: str | None = _UNSET,
    timestamp: datetime | None = None,
    event_id: str | None = None,
    session: str | None = _UNSET,
) -> bool:
    """Emite un evento. `actor_id` es el `User.id` real (se seudonimiza); `user` fija el `userId` ya calculado y
    `session`, el `sessionId` (por defecto, el de la petición).

    Devuelve si el evento se ha entregado. Nunca lanza.
    """
    try:
        context = current_context()
        source = "backend" if context else "internal_process"
        envelope = {
            "eventId": event_id or str(uuid.uuid4()),
            "timestamp": format_timestamp(timestamp or datetime.now(UTC)),
            "sessionId": (context.session_id if context else None) if session is _UNSET else session,
            "userId": user_ref(actor_id) if user is _UNSET else user,
            "event_type": event_type,
            "schemaVersion": contract.schema_version(event_type) or "",
            "requestId": context.request_id if context else None,
            "source": source,
            "environment": get_environment(),
            "properties": properties,
        }
        event = TelemetryEvent.model_validate(envelope)
    except ValidationError as error:
        reasons = [item["msg"] for item in error.errors(include_url=False, include_context=False, include_input=False)]
        logger.warning(
            "telemetry_event_dropped %s",
            json.dumps(
                {"event_type": event_type, "drop_reason": "schema_validation_failed", "errors": reasons},
                ensure_ascii=False,
            ),
        )
        return False
    except Exception:  # noqa: BLE001 — la telemetría nunca rompe la operación
        logger.exception("telemetry_event_dropped {\"event_type\": %s, \"drop_reason\": \"emitter_error\"}", event_type)
        return False
    try:
        ingest([event], channel="backend")
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo entregar el evento de telemetría %s", event_type)
        return False
    return True


# --- Inventario ------------------------------------------------------------------------------------------------


def _sku_properties(sku: Any, warehouse_code: str) -> dict[str, Any]:
    """Campos mínimos del BRIEFING (§5.1) a partir del SKU y del almacén del movimiento."""
    return {
        "warehouse": warehouse_id(warehouse_code),
        "client_id": client_slug(sku.client_name),
        "product_id": sku.sku,
        "product_category": sku.category,
    }


def emit_order_created(sku: Any, movement: Any, *, outbound: bool) -> bool:
    """`inbound_order_created`, `outbound_order_created` (despacho) o `stock_loss_recorded` (pérdida), tras el commit."""
    if not outbound:
        event_type = "inbound_order_created"
    else:
        event_type = "outbound_order_created" if movement.exit_type == "dispatch" else "stock_loss_recorded"
    created_at = movement.created_at
    return emit(
        event_type,
        {**_sku_properties(sku, movement.warehouse), "quantity": movement.quantity, "order_id": movement.id},
        actor_id=movement.user_uuid,
        timestamp=created_at,
        event_id=deterministic_event_id(event_type, movement.id, format_timestamp(created_at)),
    )


def emit_order_rejected(
    *,
    order_type: str,
    reason: str,
    quantity: int,
    actor_id: str,
    sku: Any | None = None,
    warehouse_code: str | None = None,
    available: int | None = None,
    exit_type: str | None = None,
) -> bool:
    """`inventory_order_rejected`: stock insuficiente (400) o SKU inexistente (404)."""
    code = warehouse_code or (sku.warehouse if sku is not None else None)
    product = (
        _sku_properties(sku, code or "")
        if sku is not None
        else {"warehouse": warehouse_id(code), "client_id": None, "product_id": None, "product_category": None}
    )
    return emit(
        "inventory_order_rejected",
        {
            "order_type": order_type,
            "rejection_reason": reason,
            **product,
            "quantity": quantity,
            "available_quantity": available,
            "exit_type": exit_type,
        },
        actor_id=actor_id,
    )


def emit_direct_stock_edit_rejected(
    *,
    channel: str,
    route_template: str,
    http_method: str,
    sku_id: int | None = None,
    quantity: int | None = None,
    product: dict[str, Any] | None = None,
) -> bool:
    """`direct_stock_edit_rejected` (obligatorio). El usuario sale del token si es válido (un 405 se decide antes de
    las dependencias del router, así que aquí se decodifica sin lanzar)."""
    context = current_context()
    user = user_ref_from_authorization(context.authorization if context else None)
    if product is None:
        product = {"warehouse": None, "client_id": None, "product_id": None, "product_category": None}
        if sku_id is not None:
            product = _lookup_product(sku_id) or product
    return emit(
        "direct_stock_edit_rejected",
        {
            **product,
            "quantity": quantity,
            "attempt_channel": channel,
            "route_template": route_template,
            "http_method": http_method,
            "authenticated": user is not None,
        },
        user=user,
    )


def _lookup_product(sku_id: int) -> dict[str, Any] | None:
    """Datos del SKU afectado, o `None` si no existe o la base no responde (el evento sale igualmente)."""
    from sqlmodel import Session

    from app.database import get_engine
    from app.inventory_models import SKU

    try:
        with Session(get_engine()) as session:
            sku = session.get(SKU, sku_id)
            return _sku_properties(sku, sku.warehouse) if sku is not None else None
    except Exception:  # noqa: BLE001
        return None


def product_from_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Caso 3: datos del SKU tal y como llegan en el cuerpo, solo si son valores válidos del contrato."""
    sku = body.get("sku")
    client = body.get("client_name")
    category = body.get("category")
    warehouse = body.get("warehouse")
    product_id = sku.strip() if isinstance(sku, str) and 0 < len(sku.strip()) <= 64 else None
    return {
        "warehouse": warehouse_id(warehouse.strip()) if isinstance(warehouse, str) else None,
        "client_id": client_slug(client) if isinstance(client, str) and client.strip() else None,
        "product_id": product_id,
        "product_category": category if category in ("fashion", "electronics", "cosmetics") else None,
    }


# --- Autenticación ---------------------------------------------------------------------------------------------


def emit_login_succeeded(*, user_id: str, role: str, auth_method: str) -> bool:
    return emit("login_succeeded", {"auth_method": auth_method, "user_role": role}, actor_id=user_id)


def emit_login_failed(
    *, reason: str, auth_method: str, email: str | None, inactive_user_id: str | None = None
) -> bool:
    """`login_failed`: `userId` solo con la cuenta desactivada (la contraseña era correcta); `sessionId` siempre nulo
    (no hay sesión: el login ha fallado). `account_ref` es el seudónimo HMAC del email, nunca el email."""
    return emit(
        "login_failed",
        {"failure_reason": reason, "auth_method": auth_method, "account_ref": account_ref(email)},
        user=user_ref(inactive_user_id),
        session=None,
    )
