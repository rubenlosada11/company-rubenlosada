"""Infraestructura de las pruebas unitarias de autenticación (AUTH-088, ver TESTING.md).

Se suma a `tests/conftest.py`, que ya da a todos los tests una `SECRET_KEY` de pruebas, una base de usuarios temporal
(`auth_env`, autouse), `make_user` y `bearer`. Aquí solo se añade lo que esas fixtures no cubren:

- `clock`: reloj fijo y controlable para probar caducidades sin esperas reales.
- `email_outbox`: emisor de emails falso (ningún test habla con Resend).
- `ana`, `admin`, `manager`: usuarios sintéticos de cada rol.
- `block_network` (autouse): cualquier intento de abrir una URL falla el test.
"""

import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from app.auth_models import Role
from app.main import app
from app.services.email import get_email_sender

# Instante de referencia de los tests con reloj fijo (UTC, sin microsegundos: los JWT van en segundos enteros).
T0 = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

# Módulos que leen la hora con `datetime.now(...)`. `jose.jwt` es el que valida `exp`, `iat` y `nbf` al decodificar;
# parchearlo depende de un detalle interno de python-jose, por eso `test_fixtures.py` comprueba que sigue funcionando.
CLOCK_MODULES = ("app.security", "app.services.users", "app.services.password_reset", "jose.jwt")


class _AnyDatetime(type):
    # Los módulos parcheados también usan `datetime` en `isinstance` (jose convierte así `iat`/`exp` al firmar): la
    # clase congelada debe seguir reconociendo cualquier `datetime` real.
    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime)


class FrozenClock:
    """Hora actual de los módulos de `CLOCK_MODULES` mientras dura el test. Avanza solo con `advance` o `set`."""

    def __init__(self, start: datetime):
        self.now = start

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now

    def set(self, moment: datetime) -> datetime:
        self.now = moment
        return self.now


@pytest.fixture
def clock(monkeypatch) -> FrozenClock:
    """Congela `datetime.now` en `T0` para la emisión y la validación de tokens y enlaces."""
    frozen = FrozenClock(T0)

    class FrozenDatetime(datetime, metaclass=_AnyDatetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.now if tz is None else frozen.now.astimezone(tz)

    for module in CLOCK_MODULES:
        monkeypatch.setattr(f"{module}.datetime", FrozenDatetime)
    return frozen


class FakeEmailSender:
    """Guarda los emails en lugar de enviarlos. Con `error` definido, `send` lo lanza (proveedor caído)."""

    def __init__(self):
        self.sent = []
        self.error: Exception | None = None

    def send(self, message):
        if self.error is not None:
            raise self.error
        self.sent.append(message)
        return f"fake-{len(self.sent)}"


@pytest.fixture
def email_outbox():
    """Emisor falso. Se puede pasar directamente a la función del router o, vía `TestClient`, sustituye la dependencia."""
    sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Ningún test de autenticación puede salir a la red (el envío de emails usa `urllib.request.urlopen`)."""

    def _blocked(*args, **kwargs):
        raise AssertionError("Un test de autenticación ha intentado abrir una conexión de red.")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


@pytest.fixture
def ana(make_user):
    return make_user("ana@trackflow.test")


@pytest.fixture
def admin(make_user):
    return make_user("admin@trackflow.test", Role.ADMIN)


@pytest.fixture
def manager(make_user):
    return make_user("manager@trackflow.test", Role.MANAGER)
