"""`POST /api/incidents` — registro de una incidencia (API-042, TESTING.md §10).

Reglas de `CONTEXT-gestor-incidencias.es.md` (paquete compartido `analisis_incidencias.gestor`): todos los campos son
obligatorios, título ≤ 120 y descripción ≤ 2000 caracteres tras recortar, valores de las listas cerradas. Nace en
`open` con las fechas del servidor. Los errores de validación se convierten en 400 con un mensaje en español por campo
(`to_field_error`), sin devolver el valor recibido.
"""

import pytest
from pydantic import ValidationError

from app.incident_models import IncidentStatus
from app.routes.incident_manager import create_incident, to_field_error

from .conftest import T0, incident_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_new_incident_is_open_with_server_dates_and_trimmed_texts(clock):
    result = create_incident(incident_data(title="  Paquete perdido  ", description=" Sin entregar. "))

    assert result.id == 1 and result.status == IncidentStatus.OPEN
    assert result.created_at == result.updated_at == T0
    assert (result.title, result.description) == ("Paquete perdido", "Sin entregar.")


def test_client_cannot_choose_status_dates_or_id(clock):
    result = create_incident(incident_data(status="resolved", created_at="2000-01-01T00:00:00Z", id=50))
    assert (result.id, result.status, result.created_at) == (1, IncidentStatus.OPEN, T0)


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_title_and_description_at_their_maximum_length_are_accepted():
    result = create_incident(incident_data(title=" " + "t" * 120 + " ", description="d" * 2000))
    assert (len(result.title), len(result.description)) == (120, 2000)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("title", "t" * 121, "El título no puede superar los 120 caracteres."),
        ("description", "d" * 2001, "La descripción no puede superar los 2000 caracteres."),
    ],
)
def test_one_character_over_the_maximum_is_rejected(field, value, message):
    with pytest.raises(ValidationError) as error:
        incident_data(**{field: value})
    assert message in str(error.value)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("title", "   ", "El título es obligatorio."),
        ("description", None, "La descripción es obligatoria."),
        ("category", "catering", "La categoría no es válida."),
        ("branch", "madrid_office", "La sede no es válida."),
        ("origin", 3, "El origen debe ser un texto."),
    ],
)
def test_invalid_field_gets_the_shared_spanish_message(field, value, message):
    with pytest.raises(ValidationError) as error:
        incident_data(**{field: value})
    assert message in str(error.value)


def test_validation_error_becomes_a_field_error_without_the_received_value():
    with pytest.raises(ValidationError) as error:
        incident_data(category="dato-sensible-del-cliente")
    (field_error,) = [to_field_error(item) for item in error.value.errors()]

    assert field_error["field"] == "category"
    assert field_error["msg"].startswith("La categoría no es válida. Valores admitidos: lost_parcel")
    assert "dato-sensible-del-cliente" not in str(field_error)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"type": "missing", "loc": ("body", "title")}, "El título es obligatorio."),
        ({"type": "json_invalid", "loc": ("body", 12)}, "El cuerpo de la petición no es un JSON válido."),
        ({"type": "int_parsing", "loc": ("path", "incident_id"), "input": "abc"}, "El identificador debe ser un número entero."),
        ({"type": "otro", "loc": ("body", "campo_desconocido")}, "Valor no válido."),
    ],
    ids=["campo-ausente", "json-invalido", "id-no-numerico", "desconocido"],
)
def test_framework_errors_are_translated_to_spanish(error, expected):
    assert to_field_error(error)["msg"] == expected
