import pytest
from fastapi.testclient import TestClient

from app.database import suppliers_table
from app.main import app
from app.seed import seed


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Base de datos TinyDB temporal y aislada para cada test (nunca toca `db/suppliers.json`)."""
    path = tmp_path / "db" / "suppliers.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(path))
    return path


@pytest.fixture
def client(db_path):
    """Cliente HTTP contra la API con la base temporal vacía."""
    return TestClient(app)


@pytest.fixture
def seeded_client(client):
    """Cliente HTTP con los 15 proveedores del CONTEXT cargados (ids 1–15, en el orden del seed)."""
    with suppliers_table() as table:
        seed(table)
    return client
