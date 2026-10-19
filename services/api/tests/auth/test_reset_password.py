"""`POST /auth/reset-password` — fijar una contraseña nueva con el enlace del email (AUTH-088, TESTING.md §6, fila 7).

Los enlaces se emiten con el servicio real (`issue_reset_token`) y se usan llamando a la función del router
(`reset_password`). El reloj está congelado (`clock`) para fijar el instante exacto de caducidad. `hash_password` se
envuelve con un espía que llama a la función real, solo para contar si se gastó un bcrypt.
"""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth_models import ResetPasswordRequest
from app.dependencies import get_current_user
from app.routes import auth as auth_routes
from app.routes.auth import INVALID_RESET_LINK, PASSWORD_RESET_DONE, authenticate, reset_password
from app.security import create_access_token
from app.services import users as users_service
from app.services.password_reset import ResetTokenStatus, issue_reset_token, reset_token_status
from conftest import PASSWORD

from .conftest import T0

NEW_PASSWORD = "contraseña-nueva-2026"
LIFETIME = timedelta(minutes=30)


def reset(token: str, new_password: str = NEW_PASSWORD) -> str:
    return reset_password(ResetPasswordRequest(token=token, new_password=new_password)).message


def rejected(token: str, new_password: str = NEW_PASSWORD) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        reset(token, new_password)
    assert (error.value.status_code, error.value.detail) == (400, INVALID_RESET_LINK)
    return error.value


def can_log_in(password: str) -> bool:
    try:
        authenticate("ana@trackflow.test", password)
    except HTTPException:
        return False
    return True


def tampered(token: str) -> str:
    return token[:-1] + ("A" if token[-1] != "A" else "B")


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_valid_link_changes_the_password_uses_the_link_and_closes_sessions(clock, ana):
    session, _ = create_access_token(ana.id)  # sesión abierta en T0
    token = issue_reset_token(ana.id).token
    clock.advance(seconds=5)

    assert reset(token) == PASSWORD_RESET_DONE

    assert can_log_in(NEW_PASSWORD) and not can_log_in(PASSWORD)
    assert reset_token_status(token) is ResetTokenStatus.USED
    with pytest.raises(HTTPException) as error:
        get_current_user(session)  # la sesión anterior (o la de quien robara el token) se cierra
    assert error.value.status_code == 401


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_link_works_until_the_instant_before_it_expires(clock, ana):
    token = issue_reset_token(ana.id).token
    clock.set(T0 + LIFETIME - timedelta(microseconds=1))
    assert reset(token) == PASSWORD_RESET_DONE


def test_link_is_expired_exactly_at_expires_at(clock, ana):
    token = issue_reset_token(ana.id).token
    clock.set(T0 + LIFETIME)
    rejected(token)
    assert can_log_in(PASSWORD)


@pytest.mark.parametrize(
    "new_password",
    ["a" * 8, "ñ" * 36, "  frase de paso con espacios  "],
    ids=["8-caracteres", "72-bytes", "espacios-en-los-extremos"],
)
def test_new_passwords_at_the_limits_work_exactly_as_typed(ana, new_password):
    reset(issue_reset_token(ana.id).token, new_password)
    assert can_log_in(new_password)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


def test_link_cannot_be_used_twice(clock, ana):
    token = issue_reset_token(ana.id).token
    reset(token)
    rejected(token, "otra-contraseña-distinta")
    assert can_log_in(NEW_PASSWORD)


@pytest.mark.parametrize("kind", ["manipulado", "inventado", "vacio"])
def test_unknown_or_tampered_link_changes_nothing(ana, kind):
    real = issue_reset_token(ana.id).token
    token = {"manipulado": tampered(real), "inventado": "x" * 43, "vacio": ""}[kind]
    rejected(token)
    assert can_log_in(PASSWORD)
    assert reset_token_status(real) is ResetTokenStatus.VALID


def test_link_from_a_previous_request_is_no_longer_valid(clock, ana):
    old = issue_reset_token(ana.id).token
    clock.advance(seconds=60)
    new = issue_reset_token(ana.id).token
    rejected(old)
    assert reset(new) == PASSWORD_RESET_DONE


def test_link_of_a_deactivated_user_is_rejected(ana):
    token = issue_reset_token(ana.id).token
    users_service.update_user(ana.id, {"is_active": False})
    rejected(token)
    users_service.update_user(ana.id, {"is_active": True})
    assert can_log_in(PASSWORD)


@pytest.mark.parametrize("new_password", ["a" * 7, "ñ" * 37], ids=["corta", "73-bytes"])
def test_invalid_new_password_is_rejected_without_using_the_link(ana, new_password):
    token = issue_reset_token(ana.id).token
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token=token, new_password=new_password)
    assert reset_token_status(token) is ResetTokenStatus.VALID


def test_invalid_link_is_rejected_before_spending_cpu_on_bcrypt(ana, monkeypatch):
    calls = []
    real_hash = auth_routes.hash_password
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: calls.append(1) or real_hash(password))

    rejected("x" * 43)
    assert calls == []
