"""`PATCH /api/incidents/{id}/status` — máquina de estados (API-042, TESTING.md §10).

Solo `open → in_progress | discarded` e `in_progress → resolved | discarded`; `resolved` y `discarded` son finales.
Una transición no permitida responde 400 con el motivo en el campo `status`. Cada cambio renueva `updated_at`.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.incident_models import IncidentStatus, IncidentStatusUpdate
from app.routes.incident_manager import create_incident, get_incident, update_status

from .conftest import T0, incident_data


def move(incident_id: int, status: str):
    return update_status(incident_id, IncidentStatusUpdate(status=status))


def refused(incident_id: int, status: str) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        move(incident_id, status)
    assert error.value.status_code == 400
    (detail,) = error.value.detail
    assert detail["field"] == "status"
    return detail


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_open_to_in_progress_to_resolved_renews_updated_at(clock):
    incident = create_incident(incident_data())

    started = move(incident.id, "in_progress")
    assert started.updated_at == T0
    resolved_at = clock.advance(hours=2)
    resolved = move(incident.id, "resolved")

    assert resolved.status == IncidentStatus.RESOLVED
    assert (resolved.created_at, resolved.updated_at) == (T0, resolved_at)


# --- Casos límite -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", [["discarded"], ["in_progress", "discarded"]], ids=["desde-open", "desde-in-progress"])
def test_an_incident_can_be_discarded_from_both_non_final_states(path):
    incident = create_incident(incident_data())
    for status in path:
        result = move(incident.id, status)
    assert result.status == IncidentStatus.DISCARDED


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("final", ["resolved", "discarded"])
def test_final_states_admit_no_more_changes(final):
    incident = create_incident(incident_data())
    if final == "resolved":
        move(incident.id, "in_progress")
    move(incident.id, final)

    detail = refused(incident.id, "in_progress")

    assert f"estado final ({final})" in detail["msg"]
    assert get_incident(incident.id).status == final


def test_skipping_in_progress_is_not_allowed_and_explains_the_valid_options():
    incident = create_incident(incident_data())
    detail = refused(incident.id, "resolved")
    assert detail["msg"] == "No se puede pasar de open a resolved. Desde open solo se admite: in_progress, discarded."


def test_moving_to_the_current_state_is_refused():
    incident = create_incident(incident_data())
    assert refused(incident.id, "open")["msg"] == "La incidencia ya está en estado open."


def test_status_of_a_missing_incident_is_404():
    with pytest.raises(HTTPException) as error:
        move(5, "in_progress")
    assert (error.value.status_code, error.value.detail) == (404, "Incidencia 5 no encontrada")


@pytest.mark.parametrize("value", ["closed", "", None])
def test_unknown_status_is_rejected_by_the_model(value):
    with pytest.raises(ValidationError):
        IncidentStatusUpdate(status=value)
