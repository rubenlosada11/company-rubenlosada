"""`GET /api/incidents/summary` — totales del gestor (API-042, TESTING.md §10).

Cada bloque (estado, categoría, origen, sede) incluye **todos** los valores posibles, a 0 si no hay incidencias: el
dashboard no tiene que adivinar qué claves existen. El caso de fallo usa `TestClient` porque lo que se comprueba es que
la ruta está protegida por el router (`dependencies=[Depends(get_current_user)]`) y que `/summary` no se confunde con
un id.
"""

from fastapi.testclient import TestClient

from app.incident_models import Branch, IncidentCategory, IncidentOrigin, IncidentStatus, IncidentStatusUpdate
from app.main import app
from app.routes.incident_manager import create_incident, get_summary, update_status

from .conftest import incident_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_summary_counts_by_every_dimension():
    create_incident(incident_data())
    create_incident(incident_data(category="carrier_issue", branch="la_office"))
    discarded = create_incident(incident_data(origin="internal"))
    update_status(discarded.id, IncidentStatusUpdate(status="discarded"))

    summary = get_summary()

    assert summary.total == 3
    assert summary.by_status[IncidentStatus.OPEN] == 2 and summary.by_status[IncidentStatus.DISCARDED] == 1
    assert summary.by_category[IncidentCategory.LOST_PARCEL] == 2
    assert summary.by_branch[Branch.LA_OFFICE] == 1
    assert summary.by_origin[IncidentOrigin.INTERNAL] == 1
    assert sum(summary.by_status.values()) == summary.total


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_empty_database_reports_every_value_at_zero():
    summary = get_summary()
    assert summary.total == 0
    assert set(summary.by_status) == set(IncidentStatus) and set(summary.by_branch) == set(Branch)
    assert set(summary.by_category) == set(IncidentCategory) and set(summary.by_origin) == set(IncidentOrigin)
    blocks = (summary.by_status, summary.by_category, summary.by_origin, summary.by_branch)
    assert all(count == 0 for block in blocks for count in block.values())


# --- Modo de fallo ------------------------------------------------------------------------------------------------


def test_summary_requires_a_session():
    response = TestClient(app).get("/api/incidents/summary")
    assert response.status_code == 401
