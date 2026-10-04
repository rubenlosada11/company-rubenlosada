"""Seed del gestor de incidencias (`scripts/seed_incidents.py`): se prueba aquí porque necesita TinyDB y los modelos."""

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest
from analisis_incidencias import parsear_csv
from analisis_incidencias.dominio import CAMPOS

from app.database import incidents_table
from app.incident_models import IncidentRecord
from app.services.incidents import insert_incident, to_incident

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "seed_incidents.py"
CSV = ROOT / "scripts" / "incidents-trackflow.csv"

spec = importlib.util.spec_from_file_location("seed_incidents", SCRIPT)
seed_incidents = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = seed_incidents  # `dataclass` busca el módulo ahí al resolver las anotaciones
spec.loader.exec_module(seed_incidents)

CABECERA = ",".join(CAMPOS)
FILA = "TRF-000001,2024-01-08,ES,B2C,ES12345678,SEUR,DAMAGE,Caja aplastada en el reparto,CLOSED,persona@example.com,4"


def filas(*lineas: str):
    return parsear_csv("\n".join([CABECERA, *lineas]))


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = seed_incidents.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def stats(out: str) -> dict[str, int]:
    """Bloque de estadísticas de la salida: `{"Insertadas": 95, ...}`."""
    return {label: int(value) for label, value in re.findall(r"^  ([\wáí ]+):\s+(\d+)$", out, flags=re.MULTILINE)}


def stored(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["incidents"]


# --- CSV histórico: valores esperados del CONTEXT ---------------------------------------------------------------


def test_first_run_loads_the_expected_values(incidents_db_path, capsys):
    code, out, err = run(capsys)
    assert (code, err) == (0, "")
    assert stats(out) == {
        "Filas leídas": 100, "Válidas": 95, "Insertadas": 95, "Duplicadas": 0, "Inválidas": 5, "Errores": 0,
    }
    assert "Incidencias en la base: 95 (95 del CSV)" in out

    docs = list(stored(incidents_db_path).values())
    assert len(docs) == 95
    assert Counter(d["status"] for d in docs) == {"open": 29, "resolved": 52, "discarded": 14}
    assert Counter(d["category"] for d in docs) == {
        "lost_parcel": 14, "carrier_issue": 45, "delivery_failure": 19, "returns_issue": 17,
    }
    assert {d["origin"] for d in docs} == {"customer"}
    assert Counter(d["branch"] for d in docs) == {"la_office": 50, "zaragoza_office": 45}


def test_second_run_inserts_nothing(incidents_db_path, capsys):
    run(capsys)
    before = incidents_db_path.read_bytes()
    code, out, _ = run(capsys)
    assert code == 0
    assert stats(out) == {
        "Filas leídas": 100, "Válidas": 95, "Insertadas": 0, "Duplicadas": 95, "Inválidas": 5, "Errores": 0,
    }
    assert "Incidencias en la base: 95 (95 del CSV)" in out
    assert incidents_db_path.read_bytes() == before  # ni un byte cambia


def test_invalid_rows_are_reported_and_not_stored(incidents_db_path, capsys):
    _, out, _ = run(capsys)
    for incident_id, reason in (
        ("TRF-000003", "Número de seguimiento inválido"),
        ("TRF-000025", "Transportista inválido para el país"),
        ("TRF-000042", "Categoría ausente o inválida"),
        ("TRF-000068", "Email ausente o inválido"),
        ("TRF-000097", "Cerrada sin puntuación"),
    ):
        assert any(incident_id in line and reason in line for line in out.splitlines())
    ids = {d["source_id"] for d in stored(incidents_db_path).values()}
    assert not ids & {"TRF-000003", "TRF-000025", "TRF-000042", "TRF-000068", "TRF-000097"}


def test_stored_documents_follow_the_context_mapping(incidents_db_path, capsys):
    run(capsys)
    first = next(d for d in stored(incidents_db_path).values() if d["source_id"] == "TRF-000001")
    assert first["created_at"] == first["updated_at"] == "2024-01-08T00:00:00Z"  # medianoche UTC
    assert first["title"] == first["description"]  # menos de 120 caracteres: el título es la descripción
    assert (first["category"], first["branch"], first["origin"]) == ("returns_issue", "zaragoza_office", "customer")
    assert set(first) == {
        "title", "description", "category", "status", "origin", "branch", "created_at", "updated_at", "source_id",
    }


def test_no_customer_emails_anywhere(incidents_db_path, capsys):
    _, out, err = run(capsys)
    assert "@" not in out + err
    assert "@" not in incidents_db_path.read_text(encoding="utf-8")


def test_api_model_reads_the_seeded_documents_without_source_id(capsys):
    run(capsys)
    with incidents_table() as table:
        incidents = [to_incident(doc) for doc in table.all()]
    assert len(incidents) == 95
    assert all("source_id" not in incident.model_dump() for incident in incidents)


# --- Idempotencia y casos límite --------------------------------------------------------------------------------


def test_only_missing_rows_are_inserted():
    otra = FILA.replace("TRF-000001", "TRF-000002")
    with incidents_table() as table:
        first = seed_incidents.seed(table, filas(FILA))
        second = seed_incidents.seed(table, filas(FILA, otra))
        assert (first.insertadas, first.duplicadas) == (1, 0)
        assert (second.insertadas, second.duplicadas, second.validas) == (1, 1, 2)
        assert len(table) == 2


def test_repeated_id_inside_the_same_file_is_inserted_once():
    with incidents_table() as table:
        result = seed_incidents.seed(table, filas(FILA, FILA))
        assert (result.leidas, result.insertadas, result.duplicadas) == (2, 1, 1)
        assert len(table) == 1


def test_does_not_overwrite_changes_made_after_the_seed():
    abierta = FILA.replace("CLOSED", "OPEN").replace(",4", ",")
    with incidents_table() as table:
        seed_incidents.seed(table, filas(abierta))
        table.update({"status": "in_progress"}, doc_ids=[1])
        result = seed_incidents.seed(table, filas(abierta))
        assert result.duplicadas == 1
        assert table.get(doc_id=1)["status"] == "in_progress"


def test_manual_incidents_are_kept_and_never_count_as_duplicates(capsys):
    manual = IncidentRecord.model_validate({
        "title": "Caja aplastada en el reparto", "description": "Caja aplastada en el reparto",
        "category": "carrier_issue", "status": "open", "origin": "customer", "branch": "zaragoza_office",
        "created_at": "2024-01-08T00:00:00Z", "updated_at": "2024-01-08T00:00:00Z",
    })
    with incidents_table() as table:
        insert_incident(table, manual)
    _, out, _ = run(capsys)
    assert stats(out)["Insertadas"] == 95
    assert "Incidencias en la base: 96 (95 del CSV)" in out


@pytest.mark.parametrize(
    ("fila", "motivo"),
    [
        (FILA.replace("TRF-000001", ""), "ID de incidencia inválido"),
        (FILA.replace("2024-01-08", "08/01/2024"), "Fecha ausente o inválida"),
        (FILA.replace("CLOSED", "closed"), "Estado ausente o inválido"),
        (FILA.replace(",ES,", ",FR,"), "País ausente o inválido"),
        (FILA.replace("Caja aplastada en el reparto", ""), "Descripción ausente o muy corta"),
        (FILA + ",sobra", "Número de columnas incorrecto"),
    ],
)
def test_rows_rejected_by_the_shared_validation(fila, motivo):
    with incidents_table() as table:
        result = seed_incidents.seed(table, filas(fila))
        assert (result.validas, result.insertadas, len(table)) == (0, 0, 0)
    assert motivo in result.invalidas[0].motivos


def test_long_description_gives_a_120_character_title():
    larga = "x" * 200
    with incidents_table() as table:
        seed_incidents.seed(table, filas(FILA.replace("Caja aplastada en el reparto", larga)))
        doc = table.get(doc_id=1)
    assert doc["title"] == "x" * 120 and doc["description"] == larga


def test_a_write_error_is_counted_and_does_not_stop_the_rest(monkeypatch, capsys):
    real = seed_incidents.insert_incident

    def flaky(table, record):
        if record.source_id == "TRF-000001":
            raise OSError("disco lleno")
        return real(table, record)

    monkeypatch.setattr(seed_incidents, "insert_incident", flaky)
    code, out, err = run(capsys)
    assert code == 1
    assert (stats(out)["Insertadas"], stats(out)["Errores"]) == (94, 1)
    assert "TRF-000001" in err and "OSError" in err and "Traceback" not in err


# --- Errores de fichero -----------------------------------------------------------------------------------------


def test_missing_file(incidents_db_path, tmp_path, capsys):
    code, out, err = run(capsys, str(tmp_path / "no-existe.csv"))
    assert code == 1 and "El fichero no existe" in err and out == ""
    assert not incidents_db_path.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "El fichero está vacío"),
        (CABECERA + "\n", "no contiene registros"),
        ("a,b,c\n1,2,3\n", "Faltan columnas obligatorias"),
    ],
)
def test_unusable_files(incidents_db_path, tmp_path, capsys, content, message):
    path = tmp_path / "malo.csv"
    path.write_text(content, encoding="utf-8")
    code, _, err = run(capsys, str(path))
    assert code == 1 and message in err
    assert not incidents_db_path.exists()
