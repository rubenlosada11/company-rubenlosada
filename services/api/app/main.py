import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.errors import UnexpectedErrorMiddleware, unexpected_error, validation_error
from app.routes import auth, incident_manager, incidents, inventory, profiles, suppliers, users
from app.security import ConfigError, check_auth_config
from app.services.email import check_email_config
from app.timing import RequestTimingMiddleware

# Orígenes del navegador autorizados (lista separada por comas). Por defecto, el backoffice local (puerto 3002).
DEFAULT_CORS_ORIGINS = "http://localhost:3002,http://127.0.0.1:3002"

# Logs propios (`trackflow.*`) a INFO, p. ej. el resumen de cada análisis de incidencias. El logger raíz no se toca.
trackflow_logger = logging.getLogger("trackflow")
if not trackflow_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    trackflow_logger.addHandler(handler)
    trackflow_logger.setLevel(logging.INFO)


class UTF8JSONResponse(JSONResponse):
    # Sin `charset`, Windows PowerShell 5.1 (Invoke-RestMethod) decodifica como ISO-8859-1: "MRW EspaÃ±a".
    media_type = "application/json; charset=utf-8"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        # Sin SECRET_KEY válida la API no arranca: mejor un error claro al iniciar que un 500 en el primer login.
        check_auth_config()
        # Igual con el email: clave de Resend sin remitente → error al arrancar, no en cada envío.
        check_email_config()
    except ConfigError as error:
        # El servidor imprime además la traza del arranque fallido: esta línea deja el motivo a la vista.
        trackflow_logger.error("La API no puede arrancar: %s", error)
        raise
    yield


app = FastAPI(
    title="TrackFlow API",
    description=(
        "Directorio de proveedores de TrackFlow (USA + Spain), analizador de incidencias de CX, gestor de "
        "incidencias e inventario unificado de los almacenes de Los Ángeles y Zaragoza (`/inventory`). "
        "Autenticación con Bearer JWT: `POST /auth/login` (o el botón «Authorize»)."
    ),
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
)

# Se registra antes que CORS para quedar dentro de él (el último middleware añadido es el más externo): así el 500
# genérico de un error no controlado lleva las cabeceras CORS y el backoffice puede leerlo.
app.add_middleware(UnexpectedErrorMiddleware)

# Tiempo de cada petición (`app/timing.py`). Por fuera del anterior: registra el estado final, también el 500 genérico.
app.add_middleware(RequestTimingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # `Authorization`: el backoffice envía el Bearer token. Sin cookies: no hace falta `allow_credentials`.
    allow_headers=["Content-Type", "Authorization"],
    # Sin esto, el navegador no deja leer el nombre del fichero en la descarga de /api/incidents/results/export.
    expose_headers=["Content-Disposition"],
)

# Último análisis de incidencias correcto. Vive en memoria mientras la API está en marcha (un solo proceso).
app.state.ultimo_analisis = None

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(suppliers.router)
app.include_router(incidents.router)
app.include_router(incident_manager.router)
app.include_router(inventory.router)


# Errores que no gestiona ningún router (ver `app/errors.py`): 422 sin los valores recibidos y, como último recurso
# si algo falla fuera de `UnexpectedErrorMiddleware`, 500 genérico (Starlette lo ejecuta fuera de CORS).
app.add_exception_handler(RequestValidationError, validation_error)
app.add_exception_handler(Exception, unexpected_error)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@app.get("/health", tags=["health"], response_model=HealthResponse)
def health() -> HealthResponse:
    """Comprobación de vida (healthcheck de Docker). Pública y sin datos."""
    return HealthResponse(status="ok")
