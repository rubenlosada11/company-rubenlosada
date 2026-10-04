"""Incidencias (`Incident`) en TinyDB.

Las funciones con `table` como primer parámetro trabajan dentro de una tabla ya abierta (y bajo su candado); las
demás abren y cierran la base en cada operación.
"""

from collections import Counter

from analisis_incidencias import gestor
from tinydb.table import Document, Table

from app.database import incidents_table
from app.incident_models import (
    Branch,
    Incident,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentRecord,
    IncidentStatus,
    IncidentSummary,
)
from app.models import utc_now


class InvalidTransition(Exception):
    """El cambio de estado pedido no está entre las transiciones permitidas."""


def insert_incident(table: Table, record: IncidentRecord) -> int:
    """Guarda una incidencia ya validada y devuelve su `id` (el `doc_id` de TinyDB)."""
    return table.insert(record.model_dump(mode="json", exclude_none=True))


def to_incident(doc: Document) -> Incident:
    """Documento de TinyDB → modelo de respuesta (sin `source_id`)."""
    return Incident.model_validate({**doc, "id": doc.doc_id})


def create_incident(payload: IncidentCreate) -> Incident:
    now = utc_now()
    record = IncidentRecord(**payload.model_dump(), status=IncidentStatus.OPEN, created_at=now, updated_at=now)
    with incidents_table() as table:
        return to_incident(table.get(doc_id=insert_incident(table, record)))


def list_incidents(**filters: str | None) -> list[Incident]:
    """Incidencias que cumplen todos los filtros indicados (`status`, `origin`, `branch`, `category`)."""
    active = {field: value for field, value in filters.items() if value is not None}
    with incidents_table() as table:
        docs = [doc for doc in table.all() if all(doc[field] == value for field, value in active.items())]
    incidents = [to_incident(doc) for doc in docs]
    return sorted(incidents, key=lambda incident: (incident.created_at, incident.id), reverse=True)


def get_incident(incident_id: int) -> Incident | None:
    with incidents_table() as table:
        doc = table.get(doc_id=incident_id)
    return to_incident(doc) if doc is not None else None


def update_status(incident_id: int, new_status: IncidentStatus) -> Incident | None:
    """Cambia el estado si la transición está permitida y renueva `updated_at`. None si la incidencia no existe.

    Comprobar y escribir ocurren bajo el mismo candado: dos peticiones simultáneas no pueden aplicar ambas una
    transición desde el mismo estado.
    """
    with incidents_table() as table:
        doc = table.get(doc_id=incident_id)
        if doc is None:
            return None
        reason = gestor.validar_transicion(doc["status"], new_status.value)
        if reason:
            raise InvalidTransition(reason)
        # El documento modificado pasa por el mismo modelo que el alta y el seed antes de escribirse.
        record = IncidentRecord.model_validate({**doc, "status": new_status, "updated_at": utc_now()})
        table.update(record.model_dump(mode="json", include={"status", "updated_at"}), doc_ids=[incident_id])
        return to_incident(table.get(doc_id=incident_id))


def summarize() -> IncidentSummary:
    with incidents_table() as table:
        docs = table.all()

    def count(field: str, values: type) -> dict:
        found = Counter(doc[field] for doc in docs)
        return {value: found[value.value] for value in values}

    return IncidentSummary(
        total=len(docs),
        by_status=count("status", IncidentStatus),
        by_category=count("category", IncidentCategory),
        by_origin=count("origin", IncidentOrigin),
        by_branch=count("branch", Branch),
    )
