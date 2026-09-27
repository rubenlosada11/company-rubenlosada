import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import suppliers

# Orígenes del navegador autorizados (lista separada por comas). Por defecto, el backoffice local (puerto 3002).
DEFAULT_CORS_ORIGINS = "http://localhost:3002,http://127.0.0.1:3002"


class UTF8JSONResponse(JSONResponse):
    # Sin `charset`, Windows PowerShell 5.1 (Invoke-RestMethod) decodifica como ISO-8859-1: "MRW EspaÃ±a".
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="TrackFlow API",
    description="Directorio de proveedores de TrackFlow (USA + Spain).",
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
)

app.include_router(suppliers.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
