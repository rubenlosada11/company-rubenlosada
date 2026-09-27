import pytest


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Base de datos TinyDB temporal y aislada para cada test (nunca toca `db/suppliers.json`)."""
    path = tmp_path / "db" / "suppliers.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(path))
    return path
