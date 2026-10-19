"""`POST /auth/token` — login con formulario OAuth2, el que usa «Authorize» en `/docs` (AUTH-088, TESTING.md §6, fila 3).

Se llama a la función del router (`login_form`) con un `OAuth2PasswordRequestForm` construido a mano: el formulario no
pasa por `LoginRequest`, así que la normalización del email (`username`) es responsabilidad de este router y es lo
que distingue este endpoint del login JSON.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.auth_models import LoginRequest
from app.routes.auth import BAD_CREDENTIALS, INACTIVE_ACCOUNT, login, login_form
from app.security import decode_access_token
from app.services import users as users_service
from conftest import PASSWORD


def form(username: str, password: str) -> OAuth2PasswordRequestForm:
    return OAuth2PasswordRequestForm(username=username, password=password)


def rejected(username: str, password: str) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        login_form(form(username, password))
    return error.value


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_form_login_returns_the_same_kind_of_token_as_the_json_login(ana):
    from_form = login_form(form("ana@trackflow.test", PASSWORD))
    from_json = login(LoginRequest(email="ana@trackflow.test", password=PASSWORD))

    assert from_form.token_type == from_json.token_type == "bearer"
    assert from_form.expires_in == from_json.expires_in
    assert decode_access_token(from_form.access_token)["sub"] == ana.id


# --- Caso límite --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("username", ["ANA@TrackFlow.Test", "  ana@trackflow.test  "], ids=["mayusculas", "espacios"])
def test_username_is_normalized_like_the_email_of_the_json_login(ana, username):
    token = login_form(form(username, PASSWORD))
    assert decode_access_token(token.access_token)["sub"] == ana.id


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("username", "password"),
    [("ana@trackflow.test", "no-es-la-contraseña"), ("nadie@trackflow.test", PASSWORD)],
    ids=["contraseña-incorrecta", "email-inexistente"],
)
def test_bad_credentials_get_the_generic_401_with_bearer_challenge(ana, username, password):
    error = rejected(username, password)
    assert (error.status_code, error.detail) == (401, BAD_CREDENTIALS)
    assert error.headers == {"WWW-Authenticate": "Bearer"}


def test_deactivated_account_is_403(ana):
    users_service.update_user(ana.id, {"is_active": False})
    error = rejected("ana@trackflow.test", PASSWORD)
    assert (error.status_code, error.detail) == (403, INACTIVE_ACCOUNT)
