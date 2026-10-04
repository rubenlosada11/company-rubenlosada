"""Endpoints del gestor de incidencias (`/api/incidents`). Contexto: CONTEXT-gestor-incidencias.es.md.

Comparten prefijo con el analizador (`routes/incidents.py`: `/analyze` y `/results/export`), sin solaparse.
Todos requieren un usuario autenticado (Bearer JWT).

`/summary` se declara antes de `/{incident_id}`.

Errores, solo en este router: los datos no válidos responden 400 (no el 422 por defecto de FastAPI) con un mensaje
en español por campo, y cualquier error inesperado responde 500 con un mensaje genérico (la traza queda en el log).
"""

import logging
from collections.abc import Callable
from typing import Any

from analisis_incidencias import gestor
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.dependencies import get_current_user
from app.incident_models import (
    Branch,
    Incident,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentStatus,
    IncidentStatusUpdate,
    IncidentSummary,
)
from app.services import incidents as incidents_service

logger = logging.getLogger("trackflow.api.incident_manager")

ERROR_INTERNO = "Error interno del servidor."
JSON_UTF8 = "application/json; charset=utf-8"

MENSAJES_POR_TIPO = {
    "json_invalid": "El cuerpo de la petición no es un JSON válido.",
    "model_attributes_type": "El cuerpo de la petición debe ser un objeto JSON.",
    "dict_type": "El cuerpo de la petición debe ser un objeto JSON.",
    "int_parsing": "El identificador debe ser un número entero.",
}


def to_field_error(error: dict[str, Any]) -> dict[str, Any]:
    """Error de validación de FastAPI → `{field, loc, msg}` con el mensaje en español y sin el valor recibido."""
    loc = list(error.get("loc", ()))
    path = [part for part in loc if part not in ("body", "query", "path")]
    field = str(path[0]) if path else None
    kind = error.get("type", "")

    if kind == "value_error":  # mensajes de la validación compartida (ya en español)
        msg = str(error.get("msg", "")).removeprefix("Value error, ")
    elif kind in MENSAJES_POR_TIPO:
        msg = MENSAJES_POR_TIPO[kind]
    elif field in gestor.CAMPOS:  # campo ausente o filtro con un valor que no existe
        msg = gestor.validar_campo(field, None if kind == "missing" else error.get("input")) or "Valor no válido."
    else:
        msg = "Valor no válido."
    return {"field": field, "loc": loc, "msg": msg}


class IncidentRoute(APIRoute):
    """Ruta del gestor: 400 con errores por campo y 500 genérico, sin exponer detalles internos."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def incident_route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                detail = [to_field_error(item) for item in error.errors()]
                return JSONResponse({"detail": detail}, status.HTTP_400_BAD_REQUEST, media_type=JSON_UTF8)
            except HTTPException:
                raise
            except Exception:
                logger.exception("Error inesperado en %s %s", request.method, request.url.path)
                return JSONResponse(
                    {"detail": ERROR_INTERNO}, status.HTTP_500_INTERNAL_SERVER_ERROR, media_type=JSON_UTF8
                )

        return incident_route_handler


router = APIRouter(
    prefix="/api/incidents",
    tags=["incident manager"],
    route_class=IncidentRoute,
    dependencies=[Depends(get_current_user)],
    responses={
        400: {"description": "Datos no válidos: `detail` es una lista con `field` y `msg` por cada error"},
        401: {"description": "Sin token o con un token no válido o caducado"},
    },
)

NOT_FOUND = {404: {"description": "Incidencia no encontrada"}}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate) -> Incident:
    """Registra una incidencia. Nace en estado `open`; las fechas las pone el servidor."""
    return incidents_service.create_incident(payload)


@router.get("")
def list_incidents(
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: Branch | None = None,
    category: IncidentCategory | None = None,
) -> list[Incident]:
    """Incidencias, de la más reciente a la más antigua. Los filtros son opcionales y combinables (AND)."""
    return incidents_service.list_incidents(status=status, origin=origin, branch=branch, category=category)


# Antes de `/{incident_id}`: si no, «summary» se leería como un id.
@router.get("/summary")
def get_summary() -> IncidentSummary:
    """Totales por estado, categoría, origen y sede. Con la base vacía, todos a 0."""
    return incidents_service.summarize()


def not_found(incident_id: int) -> HTTPException:
    return HTTPException(404, detail=f"Incidencia {incident_id} no encontrada")


@router.get("/{incident_id}", responses=NOT_FOUND)
def get_incident(incident_id: int) -> Incident:
    incident = incidents_service.get_incident(incident_id)
    if incident is None:
        raise not_found(incident_id)
    return incident


@router.patch("/{incident_id}/status", responses=NOT_FOUND)
def update_status(incident_id: int, payload: IncidentStatusUpdate) -> Incident:
    """Cambia el estado. Solo `open → in_progress | discarded` e `in_progress → resolved | discarded`.

    Una transición no permitida (o desde un estado final) responde 400 con el motivo en el campo `status`.
    """
    try:
        incident = incidents_service.update_status(incident_id, payload.status)
    except incidents_service.InvalidTransition as error:
        detail = [{"field": "status", "loc": ["body", "status"], "msg": str(error)}]
        raise HTTPException(400, detail=detail) from None
    if incident is None:
        raise not_found(incident_id)
    return incident
