import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import incidents, suppliers

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


app = FastAPI(
    title="TrackFlow API",
    description="Directorio de proveedores de TrackFlow (USA + Spain) y analizador de incidencias de CX.",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    # Sin esto, el navegador no deja leer el nombre del fichero en la descarga de /api/incidents/results/export.
    expose_headers=["Content-Disposition"],
)

# Último análisis de incidencias correcto. Vive en memoria mientras la API está en marcha (un solo proceso).
app.state.ultimo_analisis = None

app.include_router(suppliers.router)
app.include_router(incidents.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
