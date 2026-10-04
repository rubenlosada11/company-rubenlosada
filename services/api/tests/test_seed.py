import ast
import re
from datetime import datetime
from pathlib import Path

import pytest

from app.database import suppliers_table
from app.seed import SUPPLIERS_SEED, main, seed

CONTEXT_FILE = Path(__file__).resolve().parents[3] / "CONTEXT-directorio.md"


@pytest.fixture(scope="module")
def context_seed():
    """`SUPPLIERS_SEED` leído directamente de CONTEXT-directorio.md (fuente de verdad)."""
    text = CONTEXT_FILE.read_text(encoding="utf-8")
    block = re.search(r"SUPPLIERS_SEED = (\[.*?\n\])", text, re.S)
    assert block, "No se encontró SUPPLIERS_SEED en CONTEXT-directorio.md"
    return ast.literal_eval(block.group(1))


def stored_without_server_fields(doc):
    return {k: v for k, v in doc.items() if k != "updated_at" and v is not None}


def test_seed_data_matches_context_exactly(context_seed):
    assert len(context_seed) == 15
    assert SUPPLIERS_SEED == context_seed


def test_first_run_inserts_all(db_path, context_seed):
    with suppliers_table() as table:
        result = seed(table)
        docs = table.all()
    assert (len(result.inserted), len(result.skipped), result.total) == (15, 0, 15)
    assert [stored_without_server_fields(doc) for doc in docs] == context_seed


def test_records_get_server_timestamp(db_path):
    with suppliers_table() as table:
        seed(table)
        docs = table.all()
    for doc in docs:
        stamp = datetime.fromisoformat(doc["updated_at"])
        assert stamp.utcoffset().total_seconds() == 0


def test_second_run_creates_no_duplicates(db_path):
    with suppliers_table() as table:
        seed(table)
        ids_before = [doc.doc_id for doc in table.all()]
        result = seed(table)
        ids_after = [doc.doc_id for doc in table.all()]
    assert (len(result.inserted), len(result.skipped), result.total) == (0, 15, 15)
    assert ids_before == ids_after


def test_only_missing_suppliers_are_inserted(db_path):
    with suppliers_table() as table:
        seed(table)
        seur = table.get(lambda doc: doc["name"] == "SEUR")
        table.remove(doc_ids=[seur.doc_id])
        result = seed(table)
    assert result.inserted == ["SEUR (Spain)"]
    assert (len(result.skipped), result.total) == (14, 15)


def test_existing_records_are_not_overwritten(db_path):
    """Una tarifa o estado cambiados desde la API no se pisan al volver a ejecutar el seeder."""
    with suppliers_table() as table:
        seed(table)
        ups = table.get(lambda doc: doc["name"] == "UPS Ground")
        table.update({"rate_per_shipment": 8.1, "status": "suspended"}, doc_ids=[ups.doc_id])
        seed(table)
        ups_after = table.get(doc_id=ups.doc_id)
    assert (ups_after["rate_per_shipment"], ups_after["status"]) == (8.1, "suspended")


def test_match_ignores_case_and_keeps_other_suppliers(db_path):
    with suppliers_table() as table:
        table.insert({"name": "ups ground", "country": "USA"})
        table.insert({"name": "Proveedor nuevo", "country": "Spain"})
        result = seed(table)
    assert "UPS Ground (USA)" in result.skipped
    assert (len(result.inserted), result.total) == (14, 16)


def test_same_name_in_other_country_is_a_different_supplier(db_path):
    with suppliers_table() as table:
        table.insert({"name": "UPS Ground", "country": "Spain"})
        result = seed(table)
    assert "UPS Ground (USA)" in result.inserted


def test_main_prints_real_counts(db_path, capsys):
    main()
    first = capsys.readouterr().out
    main()
    second = capsys.readouterr().out
    assert "Seeder completed.\nInserted: 15\nSkipped: 0\nTotal: 15" in first
    assert "Seeder completed.\nInserted: 0\nSkipped: 15\nTotal: 15" in second
    assert "MRW España (Spain)" in first


def test_main_returns_zero_on_success(db_path, capsys):
    assert main() == 0
    assert capsys.readouterr().err == ""


def test_main_with_a_corrupt_database_exits_with_an_error_and_no_traceback(db_path, capsys):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("{corrupto", encoding="utf-8")

    assert main() == 1

    captured = capsys.readouterr()
    assert "Error: No se puede usar la base de datos" in captured.err and str(db_path) in captured.err
    assert "no contiene JSON válido" in captured.err and "Traceback" not in captured.err
    assert "Seeder completed." not in captured.out
    assert db_path.read_text(encoding="utf-8") == "{corrupto"  # no se ha tocado el fichero
