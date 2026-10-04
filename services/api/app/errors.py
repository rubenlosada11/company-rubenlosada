"""Errores de la API que no gestiona cada router: 500 genérico, 422 sin los valores recibidos y su registro en el log.

- `UnexpectedErrorMiddleware`: cualquier error no controlado responde 500 con un mensaje genérico. Va **dentro** de
  CORS (ver `main.py`), así el navegador puede leer la respuesta desde el backoffice; fuera de CORS la vería como un
  fallo de red.
- `validation_error`: el 422 de FastAPI sin `input` ni `ctx`. Por defecto devuelve el valor recibido, que en login,
  registro y cambio de contraseña es la contraseña.
- `log_unexpected`: registra el error sin volcar al log los valores que lo provocaron.
"""

import logging
import traceback
from collections.abc import Iterable
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.database import StorageError

logger = logging.getLogger("trackflow.api")

ERROR_INTERNO = "Error interno del servidor."
JSON_UTF8 = "application/json; charset=utf-8"

# Lo que el cliente necesita de cada error de validación: dónde está, qué pasa y el tipo de error.
VALIDATION_KEYS = ("type", "loc", "msg")


def internal_error_response() -> JSONResponse:
    return JSONResponse({"detail": ERROR_INTERNO}, status_code=500, media_type=JSON_UTF8)


def _failed_fields(errors: Iterable[Any]) -> str:
    """`campo (tipo de error)` de cada fallo de validación, sin el valor que no cumple."""
    return ", ".join(
        f"{'.'.join(str(part) for part in item.get('loc', ())) or '(raíz)'} ({item.get('type', '?')})"
        for item in errors
        if isinstance(item, dict)
    )


def _origin(error: BaseException) -> str:
    """Fichero, línea y función del código de la API (no de sus dependencias) por donde pasó el error en último lugar."""
    frames = traceback.extract_tb(error.__traceback__)
    own = [frame for frame in frames if "site-packages" not in frame.filename] or frames
    return f"{own[-1].filename}:{own[-1].lineno} ({own[-1].name})" if own else "origen desconocido"


def log_unexpected(log: logging.Logger, error: Exception, message: str, *args: object) -> None:
    """Registra un error no controlado con lo necesario para diagnosticarlo y sin datos personales.

    El texto de un error de validación de Pydantic incluye los valores que no cumplen el modelo (p. ej. un usuario
    guardado con su email y su hash): de esos errores solo se registran los campos, el tipo de fallo y dónde ocurrió.
    Del resto se registra la traza completa.
    """
    if isinstance(error, StorageError):
        log.error(f"{message}: %s", *args, error)
    elif isinstance(error, ValidationError):
        fields = _failed_fields(error.errors(include_url=False, include_context=False, include_input=False))
        log.error(f"{message}: datos que no cumplen el modelo %s en %s: %s", *args, error.title, _origin(error), fields)
    elif isinstance(error, ResponseValidationError):
        log.error(f"{message}: respuesta que no cumple su modelo en %s", *args, _failed_fields(error.errors()))
    else:
        log.error(message, *args, exc_info=error)


class UnexpectedErrorMiddleware:
    """Convierte en un 500 genérico cualquier error que no haya gestionado un router. La traza queda en el log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception as error:
            log_unexpected(logger, error, "Error no controlado en %s %s", scope["method"], scope["path"])
            if response_started:
                # La respuesta ya está en camino (p. ej. falla una tarea posterior): no se puede enviar otra.
                raise
            await internal_error_response()(scope, receive, send)


async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Último recurso, para un fallo fuera del middleware anterior (p. ej. en el propio CORS). Sin cabeceras CORS."""
    log_unexpected(logger, error, "Error no controlado en %s %s", request.method, request.url.path)
    return internal_error_response()


async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    """422 con `type`, `loc` y `msg` de cada error, sin el valor recibido (`input`) ni su contexto (`ctx`)."""
    detail = [{key: item[key] for key in VALIDATION_KEYS if key in item} for item in error.errors()]
    return JSONResponse({"detail": jsonable_encoder(detail)}, status_code=422, media_type=JSON_UTF8)
