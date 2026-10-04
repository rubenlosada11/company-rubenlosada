"""Modelos Pydantic del gestor de incidencias.

Fuente de verdad de campos, categorías, estados, orígenes y sedes: `CONTEXT-gestor-incidencias.es.md` (raíz del repo).
Los valores y las reglas vienen del paquete compartido `analisis-incidencias` (`gestor.py`), el mismo que usa el seed.
"""

from enum import StrEnum
from typing import Any

from analisis_incidencias import gestor
from pydantic import AwareDatetime, BaseModel, ValidationInfo, field_validator, model_validator

IncidentCategory = StrEnum("IncidentCategory", {value.upper(): value for value in gestor.CATEGORIAS})
IncidentStatus = StrEnum("IncidentStatus", {value.upper(): value for value in gestor.ESTADOS})
IncidentOrigin = StrEnum("IncidentOrigin", {value.upper(): value for value in gestor.ORIGENES})
Branch = StrEnum("Branch", {value.upper(): value for value in gestor.SEDES})


def check_field(value: Any, info: ValidationInfo) -> Any:
    """Aplica la regla compartida del campo; el mensaje (en español) es el del paquete."""
    message = gestor.validar_campo(info.field_name, value)
    if message:
        raise ValueError(message)
    return value.strip()


class IncidentCreate(BaseModel):
    """Datos que controla el cliente al registrar una incidencia. Todos son obligatorios.

    `id`, `status`, `created_at` y `updated_at` no forman parte del modelo: si el cliente los envía se ignoran.
    """

    title: str
    description: str
    category: IncidentCategory
    origin: IncidentOrigin
    branch: Branch

    _check_fields = field_validator("title", "description", "category", "origin", "branch", mode="before")(check_field)


class IncidentData(IncidentCreate):
    """Incidencia completa: datos del cliente + estado y fechas, que solo pone el servidor (o el seed)."""

    status: IncidentStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime

    _check_status = field_validator("status", mode="before")(check_field)

    @model_validator(mode="after")
    def check_dates(self) -> "IncidentData":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at no puede ser anterior a created_at")
        return self


class IncidentRecord(IncidentData):
    """Incidencia tal y como se guarda en TinyDB. Nada se escribe sin pasar por este modelo."""

    # `incident_id` del CSV histórico: solo para que el seed no duplique. La API no lo devuelve.
    source_id: str | None = None


class Incident(IncidentData):
    """Incidencia tal y como la devuelve la API."""

    id: int


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus

    _check_status = field_validator("status", mode="before")(check_field)


class IncidentSummary(BaseModel):
    """Totales del gestor. Cada bloque incluye todos los valores posibles, a 0 si no hay incidencias."""

    total: int
    by_status: dict[IncidentStatus, int]
    by_category: dict[IncidentCategory, int]
    by_origin: dict[IncidentOrigin, int]
    by_branch: dict[Branch, int]
