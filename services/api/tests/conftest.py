import pytest
from celery.backends import cache as celery_cache
from fastapi.testclient import TestClient

from app.auth_models import Role, UserCreate
from app.celery_app import celery_app
from app.cache import reset_all as reset_api_caches
from app.database import dispose_engine, suppliers_table
from app.main import app
from app.security import create_access_token
from app.seed import seed
from app.services.users import create_user
from app.tasks import registry as task_registry

# --- Celery en los tests unitarios (DEV-55) -------------------------------------------------------------------------
# Sin Redis ni worker: las tareas se ejecutan en el mismo proceso al encolarlas («eager»), con sus reintentos seguidos
# (sin esperar el backoff), y su estado se guarda en una caché en memoria para que `GET /tasks/{id}` lo lea igual que
# del result backend real. Se configura aquí, antes de que nada use `celery_app.backend`. SOLO en los tests: la
# configuración real (`app/celery_app.py`) no tiene modo eager, así que sin worker la API nunca ejecuta tareas.
# La integración con Redis y un worker reales está en tests/tasks/test_e2e_docker.py (opcional, con Docker).
celery_app.conf.update(
    broker_url="memory://",
    result_backend="cache+memory://",
    task_always_eager=True,
    task_eager_propagates=False,
    task_store_eager_result=True,
)

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
def clear_api_caches():
    """Cachés de la API (`app/cache.py`) vacías al empezar y al terminar cada test: ningún test ve datos de otro."""
    reset_api_caches()
    yield
    reset_api_caches()


@pytest.fixture(autouse=True)
def incidents_db_path(tmp_path, monkeypatch):
    """Base temporal del gestor de incidencias en todos los tests (nunca toca `db/incidents.json`)."""
    path = tmp_path / "db" / "incidents.json"
    monkeypatch.setenv("INCIDENTS_DB_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def inventory_db_url(tmp_path, monkeypatch):
    """Base SQLite temporal del inventario en todos los tests (nunca toca `db/inventory.db` ni una base real)."""
    url = f"sqlite:///{(tmp_path / 'db' / 'inventory.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    dispose_engine()


@pytest.fixture(autouse=True)
def telemetry_writes_inline(monkeypatch):
    """Los eventos de telemetría del backend se guardan en el momento, no en el hilo de escritura: así cada test
    termina con sus eventos ya en la base temporal y ninguno escribe después de que se borre."""
    monkeypatch.setattr("app.telemetry.collector.run_in_background", lambda job: job())


class FakeRedis:
    """Lo que usa `app/tasks/registry.py` de redis-py (`set`, `get`, `delete`), en memoria."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int | None] = {}

    def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self.data[name] = value
        self.ttl[name] = ex
        return True

    def get(self, name: str) -> str | None:
        return self.data.get(name)

    def delete(self, *names: str) -> int:
        return sum(self.data.pop(name, None) is not None for name in names)


@pytest.fixture(autouse=True)
def fake_task_redis(monkeypatch):
    """Registro de tareas en memoria y resultados de Celery vacíos en cada test (nunca toca un Redis real)."""
    fake = FakeRedis()
    monkeypatch.setattr(task_registry, "get_client", lambda: fake)
    celery_cache._DUMMY_CLIENT_CACHE.clear()
    yield fake
    celery_cache._DUMMY_CLIENT_CACHE.clear()


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
