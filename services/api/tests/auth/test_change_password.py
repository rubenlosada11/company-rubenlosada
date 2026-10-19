"""`POST /auth/change-password` — cambio de contraseña con sesión (AUTH-088, TESTING.md §6, fila 8).

Se llama a `change_password(payload, current_user)` con el usuario que entrega la dependencia real a partir de un
token. El reloj está congelado (`clock`) para comprobar qué sesiones sobreviven al cambio. Para el caso «usuario
borrado durante la operación» se sustituye `users_service.change_password` por una versión que primero borra al
usuario y luego llama a la función real: así se reproduce la carrera sin simular la lógica del router.
"""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth_models import ChangePasswordRequest
from app.dependencies import INVALID_TOKEN, get_current_user
from app.routes import auth as auth_routes
from app.routes.auth import WRONG_CURRENT_PASSWORD, authenticate, change_password
from app.security import create_access_token, decode_access_token
from app.services import users as users_service
from app.services.password_reset import ResetTokenStatus, issue_reset_token, reset_token_status
from conftest import PASSWORD

NEW_PASSWORD = "contraseña-nueva-2026"


def session_of(user) -> tuple[str, object]:
    token, _ = create_access_token(user.id)
    return token, get_current_user(token)


def change(current_user, current: str = PASSWORD, new: str = NEW_PASSWORD):
    return change_password(ChangePasswordRequest(current_password=current, new_password=new), current_user)


def can_log_in(email: str, password: str) -> bool:
    try:
        authenticate(email, password)
    except HTTPException:
        return False
    return True


def is_revoked(token: str) -> bool:
    try:
        get_current_user(token)
    except HTTPException as error:
        return error.status_code == 401 and error.detail == INVALID_TOKEN
    return False


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_change_with_the_right_current_password_keeps_this_session_and_closes_the_rest(clock, ana):
    old_token, user = session_of(ana)
    other_device, _ = session_of(ana)
    pending_link = issue_reset_token(ana.id).token
    clock.advance(seconds=5)

    new_token = change(user)

    assert can_log_in(ana.email, NEW_PASSWORD) and not can_log_in(ana.email, PASSWORD)
    assert get_current_user(new_token.access_token).id == ana.id  # la sesión desde la que se cambia continúa
    assert decode_access_token(new_token.access_token)["sub"] == ana.id
    assert is_revoked(old_token) and is_revoked(other_device)
    assert reset_token_status(pending_link) is ResetTokenStatus.NOT_FOUND


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_new_password_equal_to_the_current_one_is_rejected():
    with pytest.raises(ValidationError) as error:
        ChangePasswordRequest(current_password=PASSWORD, new_password=PASSWORD)
    assert "distinta de la actual" in str(error.value)


def test_token_returned_in_the_same_second_as_the_change_is_valid(clock, ana):
    _, user = session_of(ana)
    clock.advance(microseconds=900_000)  # el cambio y el token nuevo caen en el mismo segundo que la sesión
    new_token = change(user)
    assert get_current_user(new_token.access_token).id == ana.id


@pytest.mark.parametrize(
    "new_password", ["a" * 8, "ñ" * 36, "  frase de paso  "], ids=["8-caracteres", "72-bytes", "espacios"]
)
def test_new_passwords_at_the_limits_work_exactly_as_typed(ana, new_password):
    _, user = session_of(ana)
    change(user, new=new_password)
    assert can_log_in(ana.email, new_password)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current", ["no-es-la-contraseña", "", PASSWORD.upper(), "ñ" * 37], ids=["incorrecta", "vacia", "mayusculas", "73-bytes"]
)
def test_wrong_current_password_is_400_and_changes_nothing(clock, ana, current):
    token, user = session_of(ana)
    pending_link = issue_reset_token(ana.id).token

    with pytest.raises(HTTPException) as error:
        change(user, current=current)

    # 400 y no 401: la sesión es válida, lo incorrecto es un dato del formulario (el frontend no debe cerrarla).
    assert (error.value.status_code, error.value.detail) == (400, WRONG_CURRENT_PASSWORD)
    assert can_log_in(ana.email, PASSWORD)
    assert get_current_user(token).id == ana.id
    assert reset_token_status(pending_link) is ResetTokenStatus.VALID


def test_user_deleted_during_the_change_gets_401(ana, monkeypatch):
    _, user = session_of(ana)
    real_change = users_service.change_password

    def deleted_meanwhile(user_id, hashed_password):
        users_service.delete_user(user_id)
        return real_change(user_id, hashed_password)

    monkeypatch.setattr(auth_routes.users_service, "change_password", deleted_meanwhile)
    with pytest.raises(HTTPException) as error:
        change(user)
    assert (error.value.status_code, error.value.detail) == (401, INVALID_TOKEN)


def test_change_only_affects_the_owner_of_the_token(clock, ana, make_user):
    carlos = make_user("carlos@trackflow.test")
    carlos_token, _ = session_of(carlos)
    carlos_link = issue_reset_token(carlos.id).token
    _, user = session_of(ana)
    clock.advance(seconds=5)

    change(user)

    assert can_log_in(carlos.email, PASSWORD)
    assert get_current_user(carlos_token).id == carlos.id
    assert reset_token_status(carlos_link) is ResetTokenStatus.VALID


def test_new_password_that_breaks_the_rules_is_rejected():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password=PASSWORD, new_password="corta")


def test_returned_token_has_the_same_lifetime_as_a_login(ana):
    _, user = session_of(ana)
    assert change(user).expires_in == int(timedelta(minutes=30).total_seconds())
