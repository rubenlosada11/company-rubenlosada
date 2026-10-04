import pytest
from fastapi.testclient import TestClient

from app.auth_models import Role, UserCreate
from app.database import suppliers_table
from app.main import app
from app.security import create_access_token
from app.seed import seed
from app.services.users import create_user

TEST_SECRET_KEY = "clave-de-pruebas-que-no-es-secreta-0123456789"
PASSWORD = "contraseña-segura"


@pytest.fixture(autouse=True)
def auth_env(tmp_path, monkeypatch):
    """Clave JWT de pruebas y base de usuarios temporal (nunca toca `db/auth.json`) en todos los tests.

    Registro abierto por defecto: los tests del código de invitación definen `REGISTRATION_CODE` ellos mismos. Sin
    `RESEND_API_KEY`: ningún test envía un email real.
    """
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.delenv("ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)
    monkeypatch.delenv("REGISTRATION_CODE", raising=False)
    # AUTH-03: valores por defecto y sin envío real de emails, aunque el entorno del desarrollador los tenga.
    for name in ("RESET_TOKEN_EXPIRE_MINUTES", "FRONTEND_BASE_URL", "RESEND_API_KEY", "MAIL_FROM"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "db" / "auth.json"
    monkeypatch.setenv("AUTH_DB_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def incidents_db_path(tmp_path, monkeypatch):
    """Base temporal del gestor de incidencias en todos los tests (nunca toca `db/incidents.json`)."""
    path = tmp_path / "db" / "incidents.json"
    monkeypatch.setenv("INCIDENTS_DB_PATH", str(path))
    return path


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Base de datos TinyDB temporal y aislada para cada test (nunca toca `db/suppliers.json`)."""
    path = tmp_path / "db" / "suppliers.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(path))
    return path


@pytest.fixture
def make_user():
    """Crea un usuario (y su perfil) directamente en TinyDB: `make_user("ana@trackflow.test", Role.ADMIN)`."""

    def _make(email: str, role: Role = Role.USER, password: str = PASSWORD, **profile):
        user, _ = create_user(UserCreate(email=email, password=password, **profile), role=role)
        return user

    return _make


def bearer(user) -> dict[str, str]:
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def anon_client(db_path):
    """Cliente HTTP sin token."""
    return TestClient(app)


@pytest.fixture
def client(db_path, make_user):
    """Cliente HTTP autenticado (usuario con rol `user`) contra la API con la base temporal vacía."""
    user = make_user("operaciones@trackflow.test")
    return TestClient(app, headers=bearer(user))


@pytest.fixture
def seeded_client(client):
    """Cliente autenticado con los 15 proveedores del CONTEXT cargados (ids 1–15, en el orden del seed)."""
    with suppliers_table() as table:
        seed(table)
    return client
