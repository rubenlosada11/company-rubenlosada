"""Contrato de telemetría: la copia del catálogo en la API, su validador y el modelo Pydantic del envelope.

Ejecutar desde services/api: uv run pytest tests/test_telemetry_contract.py
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.telemetry import contract
from app.telemetry.models import TelemetryEvent

DOCS_SCHEMA = Path(__file__).resolve().parents[3] / "docs" / "telemetry" / "event-schemas.json"


def examples() -> list[dict]:
    schema = contract.load_schema()
    return [example for name in contract.event_types() for example in schema["definitions"][name]["examples"]]


def example(event_type: str) -> dict:
    return copy.deepcopy(contract.load_schema()["definitions"][event_type]["examples"][0])


def test_la_copia_del_catalogo_es_identica_a_la_de_docs():
    """La API valida contra su copia (la imagen Docker no incluye docs/): no puede separarse de la aprobada."""
    assert json.loads(DOCS_SCHEMA.read_text(encoding="utf-8")) == contract.load_schema()


def test_el_validador_entiende_todas_las_palabras_clave_del_catalogo():
    assert contract.unsupported_keywords() == set()


def test_catalogo_completo():
    assert len(contract.event_types()) == 43
    assert contract.catalog_version() == "1.0.0"
    assert {contract.schema_version(name) for name in contract.event_types()} == {"1.0.0"}


@pytest.mark.parametrize("event", examples(), ids=lambda event: event["event_type"])
def test_cada_ejemplo_del_catalogo_es_valido(event):
    """El receptor no puede rechazar un evento válido del catálogo: los 43 ejemplos pasan por el modelo."""
    assert contract.validate_event(event) == []
    assert TelemetryEvent.model_validate(event).to_contract() == event


def test_event_type_fuera_del_catalogo():
    event = example("navigation_section_viewed")
    event["event_type"] = "page_viewed"
    assert contract.validate_event(event) == ["event_type: no está en el catálogo aprobado"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda e: e["properties"].update(email="persona@example.com"), "propiedad no permitida por la allowlist"),
        (lambda e: e["properties"].pop("section"), "properties.section: obligatorio"),
        (lambda e: e["properties"].update(section="/inventory/orders?sku=1"), "properties.section: valor no permitido"),
        (lambda e: e.update(schemaVersion="2.0.0"), "schemaVersion: valor no permitido"),
        (lambda e: e.update(source="backend"), "source: valor no permitido"),
        (lambda e: e.update(eventId="no-es-un-uuid"), "eventId: formato no válido"),
        (lambda e: e.update(timestamp="2026-11-10 09:15:42"), "timestamp: formato no válido"),
        (lambda e: e.update(timestamp="2026-13-40T09:15:42Z"), "timestamp: formato date-time no válido"),
        (lambda e: e.update(timestamp="2026-11-10T09:15:42+01:00"), "timestamp: formato no válido"),
        (lambda e: e.update(userId="1b4e28ba-2fa1-11d2-883f-0016d3cca427"), "userId: no cumple ninguna"),
    ],
)
def test_incumplimientos_del_contrato(change, expected):
    event = example("navigation_section_viewed")
    change(event)
    errors = contract.validate_event(event)
    assert any(expected in error for error in errors), errors


def test_los_mensajes_no_repiten_el_valor_recibido():
    event = example("navigation_section_viewed")
    event["properties"]["section"] = "persona@example.com"
    event["properties"]["token"] = "secreto-123"
    errors = " ".join(contract.validate_event(event))
    assert "persona@example.com" not in errors
    assert "secreto" not in errors and "token" not in errors


def test_dolar_final_no_admite_salto_de_linea():
    """En Python `$` aceptaría un `\\n` final; en JSON Schema (ECMAScript) no."""
    event = example("navigation_section_viewed")
    event["eventId"] += "\n"
    assert contract.validate_event(event)


def test_entero_draft07_y_booleanos():
    event = example("order_history_filtered")
    event["properties"]["result_count"] = 3.0  # Draft-07: un entero puede llevar `.0`
    assert contract.validate_event(event) == []
    event["properties"]["result_count"] = True  # pero un booleano nunca es un número
    assert contract.validate_event(event)


class TestModelo:
    def test_alias_del_contrato_y_nombres_python(self):
        event = TelemetryEvent.model_validate(example("navigation_section_viewed"))
        assert event.event_id == example("navigation_section_viewed")["eventId"]
        assert event.schema_version == "1.0.0"
        assert set(event.to_contract()) == {
            "eventId", "timestamp", "sessionId", "userId", "event_type", "schemaVersion", "requestId", "source",
            "environment", "properties",
        }

    @pytest.mark.parametrize("field", ["eventId", "timestamp", "sessionId", "userId", "requestId", "properties"])
    def test_campos_obligatorios_aunque_admitan_nulo(self, field):
        event = example("navigation_section_viewed")
        del event[field]
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(event)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("timestamp", 1731230142), ("eventId", 123), ("properties", []), ("properties", "texto"), ("sessionId", 5)],
    )
    def test_tipos_estrictos(self, field, value):
        event = example("navigation_section_viewed")
        event[field] = value
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(event)

    def test_no_admite_claves_fuera_del_envelope(self):
        event = example("navigation_section_viewed")
        event["ip"] = "203.0.113.7"
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(event)

    def test_el_error_del_contrato_no_lleva_valores(self):
        event = example("navigation_section_viewed")
        event["properties"]["section"] = "persona@example.com"
        with pytest.raises(ValidationError) as caught:
            TelemetryEvent.model_validate(event)
        messages = [item["msg"] for item in caught.value.errors()]
        assert all("persona@example.com" not in message for message in messages)
