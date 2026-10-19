"""`GET /api/incidents` — listado con filtros (API-042, TESTING.md §10).

De la más reciente a la más antigua (a igual fecha, por id descendente). Los filtros `status`, `origin`, `branch` y
`category` son opcionales y se combinan con AND.
"""

import pytest

from app.incident_models import Branch, IncidentCategory, IncidentOrigin, IncidentStatus, IncidentStatusUpdate
from app.routes.incident_manager import create_incident, list_incidents, update_status

from .conftest import incident_data


def titles(result) -> list[str]:
    return [incident.title for incident in result]


@pytest.fixture
def incidents(clock):
    """Tres incidencias creadas con 1 h de diferencia; la segunda, en curso."""
    create_incident(incident_data(title="A: paquete perdido"))
    clock.advance(hours=1)
    second = create_incident(incident_data(title="B: fallo del WMS", category="system_failure", origin="internal",
                                           branch="la_warehouse"))
    update_status(second.id, IncidentStatusUpdate(status="in_progress"))
    clock.advance(hours=1)
    create_incident(incident_data(title="C: queja de cliente", category="client_complaint"))


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_lists_everything_newest_first(incidents):
    assert titles(list_incidents()) == ["C: queja de cliente", "B: fallo del WMS", "A: paquete perdido"]


def test_filters_combine_with_and(incidents):
    assert titles(list_incidents(branch=Branch.ZARAGOZA_WAREHOUSE, category=IncidentCategory.LOST_PARCEL)) == [
        "A: paquete perdido"
    ]
    assert titles(list_incidents(status=IncidentStatus.IN_PROGRESS, origin=IncidentOrigin.INTERNAL)) == [
        "B: fallo del WMS"
    ]


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_same_creation_date_is_ordered_by_id_descending(clock):
    for title in ("primera", "segunda", "tercera"):
        create_incident(incident_data(title=title))  # el reloj no avanza: misma fecha
    assert titles(list_incidents()) == ["tercera", "segunda", "primera"]


def test_filter_without_matches_gives_an_empty_list(incidents):
    assert list_incidents(status=IncidentStatus.DISCARDED) == []


def test_empty_database_gives_an_empty_list():
    assert list_incidents() == [] and list_incidents(branch=Branch.CENTRAL) == []


# --- Modo de fallo ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("enum", "value"), [(IncidentStatus, "closed"), (Branch, "madrid_office")])
def test_only_the_values_of_the_context_are_valid_filters(enum, value):
    # FastAPI convierte cada filtro con su enum: un valor desconocido responde 400 antes de filtrar.
    with pytest.raises(ValueError):
        enum(value)
