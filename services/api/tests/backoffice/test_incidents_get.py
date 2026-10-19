"""`GET /api/incidents/{id}` — consulta de una incidencia (API-042, TESTING.md §10)."""

import pytest
from fastapi import HTTPException

from app.routes.incident_manager import create_incident, get_incident

from .conftest import incident_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_get_returns_the_incident():
    created = create_incident(incident_data())
    assert get_incident(created.id) == created


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_each_id_returns_its_own_incident():
    first = create_incident(incident_data(title="primera"))
    second = create_incident(incident_data(title="segunda"))
    assert (get_incident(first.id).title, get_incident(second.id).title) == ("primera", "segunda")


# --- Modo de fallo ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("incident_id", [99, 0, -1])
def test_missing_incident_is_404_with_its_id(incident_id):
    create_incident(incident_data())
    with pytest.raises(HTTPException) as error:
        get_incident(incident_id)
    assert (error.value.status_code, error.value.detail) == (404, f"Incidencia {incident_id} no encontrada")
