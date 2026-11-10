"""Correlación de cada petición para la telemetría (plan §8.2 y §8.3) y detección de ediciones directas de stock.

`TelemetryContextMiddleware`:

- **`requestId`**: acepta el `X-Request-Id` del backoffice si es un UUID v4 válido o genera uno, y lo devuelve en la
  cabecera `X-Request-Id` de la respuesta (expuesta por CORS). Los eventos que la API emite durante la petición lo
  llevan, igual que el `form_submitted` del backoffice: así se unen.
- **`sessionId`**: lee `X-Session-Id` y lo usa solo si es un UUID válido (si no, `null`). Sirve para agrupar, nunca
  para autorizar: el cliente puede enviar cualquier valor.
- **`direct_stock_edit_rejected`** (casos 1 y 2 de la ficha): al responder una escritura sobre
  `/inventory/products/{sku_id}` con 405 (`PUT`, `PATCH`, `DELETE`: el stock no se edita) o sobre una ruta de stock que
  no existe (`/inventory/products/{id}/…`, `/inventory/stock…`) con 404. El caso 3 (campos de stock en el alta de un
  SKU) lo detecta `create_product` (`app/routes/inventory.py`).

Fuera de una petición (seeds, scripts) no hay contexto: los eventos salen con `source = internal_process`.
"""

import json
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

UUID_ANY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
UUID_V4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PRODUCT_ROUTE = "/inventory/products/{sku_id}"
# Rutas de stock que no existen (caso 2): cualquier subruta de un SKU o cualquier `/inventory/stock…`.
UNKNOWN_STOCK_ROUTE = re.compile(r"^/inventory/(products/[^/]+/.+|stock(/.*)?)$")
# Campos con los que se intenta fijar el stock (`current_stock` es el que devuelve la propia API).
STOCK_FIELDS = ("current_stock", "stock", "stock_by_warehouse")
# Solo se analiza el cuerpo de las escrituras al inventario, y solo hasta este tamaño.
MAX_CAPTURED_BODY = 64 * 1024


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    session_id: str | None
    authorization: str | None


_context: ContextVar[RequestContext | None] = ContextVar("trackflow_telemetry_context", default=None)


def current_context() -> RequestContext | None:
    return _context.get()


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1").strip()
    return None


def stock_value(body: object) -> int | None:
    """Valor de stock que se intentaba fijar: el primer entero ≥ 1 de los campos de stock del cuerpo, o `None`."""
    if not isinstance(body, dict):
        return None
    for name in STOCK_FIELDS:
        value = body.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 2_147_483_647:
            return value
    return None


class TelemetryContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = (_header(scope, b"x-request-id") or "").lower()
        session = (_header(scope, b"x-session-id") or "").lower()
        context = RequestContext(
            request_id=incoming if UUID_V4.match(incoming) else str(uuid.uuid4()),
            session_id=session if UUID_ANY.match(session) else None,
            authorization=_header(scope, b"authorization"),
        )
        token = _context.set(context)

        method = scope["method"]
        watch = method in WRITE_METHODS and scope.get("path", "").startswith("/inventory/")
        body = bytearray()
        status_code = 500
        app_receive = receive

        if watch:
            # Un 405 o un 404 se responden sin leer el cuerpo: se lee antes y se entrega intacto a la aplicación.
            buffered: list[Message] = []
            while True:
                message = await receive()
                buffered.append(message)
                if message["type"] == "http.request" and len(body) < MAX_CAPTURED_BODY:
                    body.extend(message.get("body", b"")[: MAX_CAPTURED_BODY - len(body)])
                if message["type"] != "http.request" or not message.get("more_body", False):
                    break

            async def replay() -> Message:
                return buffered.pop(0) if buffered else await receive()

            app_receive = replay

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", context.request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, app_receive, send_with_request_id)
        finally:
            if watch:
                _report_direct_stock_edit(scope, method, status_code, bytes(body))
            _context.reset(token)


def _report_direct_stock_edit(scope: Scope, method: str, status_code: int, raw_body: bytes) -> None:
    """Casos 1 y 2 de `direct_stock_edit_rejected`. Nunca lanza (lo garantiza el emisor)."""
    from app.telemetry import emitter  # evita el import circular emitter → context

    route = getattr(scope.get("route"), "path", None)
    path = scope.get("path", "")
    if status_code == 405 and route == PRODUCT_ROUTE:
        channel, template = "method_not_allowed", PRODUCT_ROUTE
    elif status_code == 404 and route is None and UNKNOWN_STOCK_ROUTE.match(path):
        channel, template = "unknown_stock_route", "unmatched"
    else:
        return

    try:
        body = json.loads(raw_body) if raw_body else None
    except ValueError:
        body = None
    sku_id = (scope.get("path_params") or {}).get("sku_id") if route == PRODUCT_ROUTE else None
    if sku_id is None and channel == "unknown_stock_route":
        match = re.match(r"^/inventory/products/(\d+)/", path)
        sku_id = match.group(1) if match else None
    emitter.emit_direct_stock_edit_rejected(
        channel=channel,
        route_template=template,
        http_method=method,
        sku_id=int(sku_id) if isinstance(sku_id, str | int) and str(sku_id).isdigit() else None,
        quantity=stock_value(body),
    )
