import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from app.database import DEFAULT_DB_PATH, get_db_path, suppliers_table

RECORD = {"name": "MRW España", "country": "Spain", "rate_per_shipment": 4.9}


def test_default_path_is_inside_the_service(monkeypatch):
    monkeypatch.delenv("SUPPLIERS_DB_PATH", raising=False)
    assert get_db_path() == DEFAULT_DB_PATH
    assert DEFAULT_DB_PATH.parts[-3:] == ("api", "db", "suppliers.json")


def test_env_var_overrides_path(db_path):
    assert get_db_path() == db_path


def test_creates_directory_and_assigns_ids(db_path):
    assert not db_path.parent.exists()
    with suppliers_table() as table:
        first = table.insert(RECORD)
        second = table.insert({**RECORD, "name": "SEUR"})
    assert db_path.is_file()
    assert (first, second) == (1, 2)


def test_data_is_stored_as_readable_utf8_json(db_path):
    with suppliers_table() as table:
        table.insert(RECORD)
    stored = json.loads(db_path.read_text(encoding="utf-8"))
    assert stored["suppliers"]["1"]["name"] == "MRW España"
    assert "MRW España" in db_path.read_text(encoding="utf-8")


def test_data_survives_reopening(db_path):
    with suppliers_table() as table:
        doc_id = table.insert(RECORD)
    with suppliers_table() as table:
        doc = table.get(doc_id=doc_id)
    assert doc == RECORD and doc.doc_id == doc_id


def test_data_survives_a_new_process(db_path):
    """Equivale a reiniciar la API: otro intérprete de Python lee lo que escribió este."""
    with suppliers_table() as table:
        doc_id = table.insert(RECORD)
    code = (
        "import json, sys; from app.database import suppliers_table\n"
        f"with suppliers_table() as t: d = t.get(doc_id={doc_id})\n"
        "sys.stdout.buffer.write(json.dumps(d, ensure_ascii=False).encode('utf-8'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=True,
        env={**os.environ, "SUPPLIERS_DB_PATH": str(db_path)},
    )
    assert json.loads(result.stdout.decode("utf-8")) == RECORD


def test_concurrent_writes_are_not_lost(db_path):
    def insert(n):
        with suppliers_table() as table:
            return table.insert({**RECORD, "name": f"Proveedor {n}"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(insert, range(40)))
    with suppliers_table() as table:
        assert len(table) == 40
    assert sorted(ids) == list(range(1, 41))
    json.loads(db_path.read_text(encoding="utf-8"))  # el fichero sigue siendo JSON válido
