"""Modelo `Incident`, integridad y tabla TinyDB del gestor de incidencias (sin endpoints)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from analisis_incidencias import gestor
from pydantic import ValidationError

from app.database import DEFAULT_INCIDENTS_DB_PATH, get_incidents_db_path, incidents_table
from app.incident_models import (
    Branch,
    Incident,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentRecord,
    IncidentStatus,
)
from app.services.incidents import insert_incident, to_incident

VALID = {
    "title": "Paquete no localizado en el muelle 3",
    "description": "El paquete figura como recibido pero no aparece en la ubicación asignada.",
    "category": "lost_parcel",
    "origin": "branch",
    "branch": "zaragoza_warehouse",
}
NOW = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
RECORD = {**VALID, "status": "open", "created_at": NOW, "updated_at": NOW}


def errors_of(model, data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    return {str(e["loc"][0]) if e["loc"] else "_": e["msg"] for e in caught.value.errors()}


# --- Enums ------------------------------------------------------------------------------------------------------


def test_enums_use_the_shared_values():
    assert [m.value for m in IncidentCategory] == list(gestor.CATEGORIAS)
    assert [m.value for m in IncidentStatus] == list(gestor.ESTADOS)
    assert [m.value for m in IncidentOrigin] == list(gestor.ORIGENES)
    assert [m.value for m in Branch] == list(gestor.SEDES)


# --- IncidentCreate ---------------------------------------------------------------------------------------------


def test_valid_incident():
    incident = IncidentCreate.model_validate(VALID)
    assert incident.category is IncidentCategory.LOST_PARCEL
    assert incident.branch is Branch.ZARAGOZA_WAREHOUSE
    assert incident.model_dump(mode="json") == VALID


def test_strips_whitespace():
    incident = IncidentCreate.model_validate({**VALID, "title": "  Título  ", "branch": " central "})
    assert incident.title == "Título"
    assert incident.branch is Branch.CENTRAL


@pytest.mark.parametrize("field", list(VALID))
def test_every_field_is_required(field):
    missing = {key: value for key, value in VALID.items() if key != field}
    assert list(errors_of(IncidentCreate, missing)) == [field]


@pytest.mark.parametrize("field", list(VALID))
@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_values_use_the_shared_message(field, value):
    errors = errors_of(IncidentCreate, {**VALID, field: value})
    assert errors == {field: f"Value error, {gestor.OBLIGATORIO[field]}"}


def test_description_is_required():
    assert "La descripción es obligatoria." in errors_of(IncidentCreate, {**VALID, "description": ""})["description"]


@pytest.mark.parametrize("field", ["category", "origin", "branch"])
def test_unknown_values_are_rejected(field):
    errors = errors_of(IncidentCreate, {**VALID, field: "no_existe"})
    assert list(errors) == [field]
    assert gestor.NO_VALIDO[field] in errors[field]


@pytest.mark.parametrize("field", list(VALID))
@pytest.mark.parametrize("value", [123, True, ["x"]])
def test_wrong_types_are_rejected(field, value):
    assert list(errors_of(IncidentCreate, {**VALID, field: value})) == [field]


def test_title_and_description_length():
    assert "120" in errors_of(IncidentCreate, {**VALID, "title": "a" * 121})["title"]
    assert "2000" in errors_of(IncidentCreate, {**VALID, "description": "a" * 2001})["description"]
    IncidentCreate.model_validate({**VALID, "title": "a" * 120, "description": "a" * 2000})


def test_server_fields_sent_by_the_client_are_ignored():
    incident = IncidentCreate.model_validate({**VALID, "id": 99, "status": "resolved", "created_at": "2020-01-01"})
    assert set(incident.model_dump()) == set(VALID)


# --- IncidentRecord (lo que se guarda) --------------------------------------------------------------------------


def test_valid_record():
    record = IncidentRecord.model_validate(RECORD)
    assert record.status is IncidentStatus.OPEN
    assert record.source_id is None


@pytest.mark.parametrize("status", gestor.ESTADOS)
def test_record_accepts_every_status(status):
    assert IncidentRecord.model_validate({**RECORD, "status": status}).status == status


@pytest.mark.parametrize("status", ["OPEN", "closed", "", None, 1])
def test_record_rejects_invalid_status(status):
    assert list(errors_of(IncidentRecord, {**RECORD, "status": status})) == ["status"]


@pytest.mark.parametrize("field", ["status", "created_at", "updated_at"])
def test_record_requires_status_and_dates(field):
    data = {key: value for key, value in RECORD.items() if key != field}
    assert list(errors_of(IncidentRecord, data)) == [field]


def test_record_rejects_dates_without_timezone():
    naive = datetime(2026, 10, 4, 9, 30)
    assert list(errors_of(IncidentRecord, {**RECORD, "created_at": naive})) == ["created_at"]


def test_record_rejects_updated_before_created():
    errors = errors_of(IncidentRecord, {**RECORD, "updated_at": NOW - timedelta(seconds=1)})
    assert "updated_at no puede ser anterior" in errors["_"]


# --- Tabla TinyDB -----------------------------------------------------------------------------------------------


def test_default_path_is_inside_the_service(monkeypatch):
    monkeypatch.delenv("INCIDENTS_DB_PATH", raising=False)
    assert get_incidents_db_path() == DEFAULT_INCIDENTS_DB_PATH
    assert DEFAULT_INCIDENTS_DB_PATH.parts[-3:] == ("api", "db", "incidents.json")


def test_env_var_overrides_path(incidents_db_path):
    assert get_incidents_db_path() == incidents_db_path


def test_table_is_created_on_first_use(incidents_db_path):
    assert not incidents_db_path.parent.exists()
    with incidents_table() as table:
        assert len(table) == 0
        first = insert_incident(table, IncidentRecord.model_validate(RECORD))
        second = insert_incident(table, IncidentRecord.model_validate({**RECORD, "title": "Otra"}))
    assert (first, second) == (1, 2)
    assert incidents_db_path.is_file()


def test_stored_document_and_round_trip(incidents_db_path):
    with incidents_table() as table:
        doc_id = insert_incident(table, IncidentRecord.model_validate({**RECORD, "source_id": "TRF-000001"}))
    stored = json.loads(incidents_db_path.read_text(encoding="utf-8"))["incidents"][str(doc_id)]
    assert stored == {
        **VALID,
        "status": "open",
        "created_at": "2026-10-04T09:30:00Z",
        "updated_at": "2026-10-04T09:30:00Z",
        "source_id": "TRF-000001",
    }
    assert "ubicación" in incidents_db_path.read_text(encoding="utf-8")  # UTF-8 legible

    with incidents_table() as table:
        incident = to_incident(table.get(doc_id=doc_id))
    assert isinstance(incident, Incident)
    assert incident.id == doc_id and incident.created_at == NOW
    assert "source_id" not in incident.model_dump()  # la API no expone el identificador del CSV


def test_manual_incident_has_no_source_id(incidents_db_path):
    with incidents_table() as table:
        doc_id = insert_incident(table, IncidentRecord.model_validate(RECORD))
        assert "source_id" not in table.get(doc_id=doc_id)


@pytest.mark.parametrize(
    "change",
    [
        {"category": "LOST_PARCEL"},
        {"status": "CLOSED"},
        {"origin": "cliente"},
        {"branch": "US"},
        {"branch": ""},
        {"title": ""},
        {"description": ""},
        {"created_at": "ayer"},
    ],
)
def test_invalid_data_never_reaches_the_table(incidents_db_path, change):
    with incidents_table() as table:
        with pytest.raises(ValidationError):
            insert_incident(table, IncidentRecord.model_validate({**RECORD, **change}))
        assert len(table) == 0


def test_does_not_touch_the_suppliers_or_auth_files(incidents_db_path, db_path, auth_env):
    with incidents_table() as table:
        insert_incident(table, IncidentRecord.model_validate(RECORD))
    assert incidents_db_path.is_file()
    assert not db_path.exists() and not auth_env.exists()
