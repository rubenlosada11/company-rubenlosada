"""Medición del tiempo de cada petición (`RequestTimingMiddleware`) y de las consultas SQL que ejecuta.

Cada petición HTTP deja una línea en el log `trackflow.api.timing`:

    GET /inventory/products 200 4.12 ms sql=2

- La ruta es la **plantilla** de FastAPI (`/suppliers/{supplier_id}`), nunca la URL real: ni ids, ni la query string
  (filtros, tokens), ni cabeceras ni cuerpos. Una URL que no corresponde a ninguna ruta se registra como `<sin ruta>`.
- `sql=` es el número de consultas que la petición ejecutó en la base del inventario (SQLModel). Las rutas que solo
  usan TinyDB no lo llevan.
- Si la petición termina con una excepción, la línea se escribe igualmente (`try/finally`), con estado 500 y el tipo
  de error; la traza la registra `UnexpectedErrorMiddleware`.
"""

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("trackflow.api.timing")

UNMATCHED_ROUTE = "<sin ruta>"


@dataclass
class _QueryCounter:
    queries: int = 0


# Contador de la petición en curso. FastAPI ejecuta los endpoints síncronos en otro hilo con una copia del contexto:
# la copia apunta al mismo objeto, así que lo que se cuenta allí se ve aquí.
_current_counter: ContextVar[_QueryCounter | None] = ContextVar("trackflow_sql_counter", default=None)


def count_sql_query(*_: object) -> None:
    """Listener de SQLAlchemy (`before_cursor_execute`): suma una consulta a la petición en curso, si la hay."""
    counter = _current_counter.get()
    if counter is not None:
        counter.queries += 1


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or UNMATCHED_ROUTE


class RequestTimingMiddleware:
    """Mide con `time.perf_counter()` cuánto tarda cada petición HTTP y lo registra sin datos sensibles."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        error_name: str | None = None
        counter = _QueryCounter()
        token = _current_counter.set(counter)

        async def send_tracking_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_tracking_status)
        except Exception as error:
            error_name = type(error).__name__
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            _current_counter.reset(token)
            sql = f" sql={counter.queries}" if counter.queries else ""
            if error_name is None:
                logger.info("%s %s %d %.2f ms%s", scope["method"], _route_template(scope), status_code, elapsed_ms, sql)
            else:
                logger.error(
                    "%s %s %d %.2f ms%s error=%s",
                    scope["method"], _route_template(scope), status_code, elapsed_ms, sql, error_name,
                )
