"""`POST /auth/login` — login con JSON (AUTH-088, TESTING.md §6, fila 2).

Se llama a la función del router (`login`) con `LoginRequest`, contra usuarios reales en el TinyDB temporal y con
bcrypt de verdad. `create_access_token` y `burn_password_check` se envuelven con espías que **llaman a la función
real**: solo cuentan las llamadas, para comprobar que un fallo no emite token y que un email inexistente cuesta lo
mismo que una contraseña incorrecta.
"""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.auth_models import LoginRequest
from app.routes import auth as auth_routes
from app.routes.auth import BAD_CREDENTIALS, INACTIVE_ACCOUNT, login
from app.security import decode_access_token
from app.services import users as users_service
from conftest import PASSWORD

from .conftest import T0


class Spy:
    """Envuelve una función real y cuenta sus llamadas."""

    def __init__(self, function):
        self.function = function
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.function(*args, **kwargs)


@pytest.fixture
def issued_tokens(monkeypatch) -> Spy:
    spy = Spy(auth_routes.create_access_token)
    monkeypatch.setattr(auth_routes, "create_access_token", spy)
    return spy


@pytest.fixture
def dummy_checks(monkeypatch) -> Spy:
    spy = Spy(auth_routes.burn_password_check)
    monkeypatch.setattr(auth_routes, "burn_password_check", spy)
    return spy


def attempt(email: str, password: str):
    return login(LoginRequest(email=email, password=password))


def rejected(email: str, password: str) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        attempt(email, password)
    return error.value


def deactivate(user):
    users_service.update_user(user.id, {"is_active": False})


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_correct_credentials_return_a_bearer_token_for_that_user(clock, ana, issued_tokens):
    token = attempt("ana@trackflow.test", PASSWORD)

    assert token.token_type == "bearer"
    assert token.expires_in == 30 * 60  # ACCESS_TOKEN_EXPIRE_MINUTES por defecto
    claims = decode_access_token(token.access_token)
    assert claims["sub"] == ana.id
    assert claims["exp"] == int((T0 + timedelta(minutes=30)).timestamp())
    assert issued_tokens.calls == 1


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_email_with_spaces_and_capitals_logs_in(ana):
    token = attempt("  ANA@TrackFlow.Test ", PASSWORD)
    assert decode_access_token(token.access_token)["sub"] == ana.id


@pytest.mark.parametrize(
    ("email", "password"),
    [("", PASSWORD), ("ana@trackflow.test", ""), ("", "")],
    ids=["email-vacio", "contraseña-vacia", "ambos-vacios"],
)
def test_empty_fields_get_the_bad_credentials_401(ana, issued_tokens, email, password):
    error = rejected(email, password)
    assert (error.status_code, error.detail) == (401, BAD_CREDENTIALS)
    assert issued_tokens.calls == 0


def test_password_longer_than_72_bytes_is_401_not_a_server_error(ana):
    # bcrypt 5 lanza ValueError con más de 72 bytes; el login debe tratarla como incorrecta.
    error = rejected("ana@trackflow.test", "ñ" * 37)
    assert (error.status_code, error.detail) == (401, BAD_CREDENTIALS)


def test_password_is_case_sensitive(ana):
    error = rejected("ana@trackflow.test", PASSWORD.upper())
    assert error.status_code == 401


# --- Modos de fallo -----------------------------------------------------------------------------------------------


def test_wrong_password_and_unknown_email_get_the_same_answer(ana, issued_tokens):
    wrong_password = rejected("ana@trackflow.test", "no-es-la-contraseña")
    unknown_email = rejected("nadie@trackflow.test", PASSWORD)

    for error in (wrong_password, unknown_email):
        assert (error.status_code, error.detail) == (401, BAD_CREDENTIALS)
        assert error.headers == {"WWW-Authenticate": "Bearer"}
    assert issued_tokens.calls == 0


def test_unknown_email_still_runs_a_bcrypt_check(ana, dummy_checks):
    # Sin esa verificación, el email inexistente respondería ~0,25 s antes y delataría qué emails existen.
    rejected("nadie@trackflow.test", PASSWORD)
    assert dummy_checks.calls == 1

    rejected("ana@trackflow.test", "no-es-la-contraseña")
    assert dummy_checks.calls == 1  # con usuario real se verifica su propio hash


def test_deactivated_account_with_the_right_password_is_403(ana, issued_tokens):
    deactivate(ana)
    error = rejected("ana@trackflow.test", PASSWORD)
    assert (error.status_code, error.detail) == (403, INACTIVE_ACCOUNT)
    assert issued_tokens.calls == 0


def test_deactivated_account_with_a_wrong_password_does_not_reveal_its_state(ana):
    deactivate(ana)
    error = rejected("ana@trackflow.test", "no-es-la-contraseña")
    assert (error.status_code, error.detail) == (401, BAD_CREDENTIALS)
