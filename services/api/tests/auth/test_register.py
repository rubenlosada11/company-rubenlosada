"""`POST /users` — registro público (AUTH-088, TESTING.md §6, fila 1).

Se llama a la función del router (`register`) con el modelo de entrada (`UserCreate`): así se prueban sus decisiones
(rol, perfil, duplicados, código de invitación) y las reglas de la contraseña sin pasar por HTTP. La base es el TinyDB
temporal de `auth_env` y la contraseña se hashea con bcrypt de verdad.
"""

import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth_models import Role, UserCreate
from app.routes.auth import authenticate
from app.routes.users import EMAIL_TAKEN, INVALID_INVITATION, register
from app.security import verify_password
from app.services.users import get_user_by_email, list_users

EMAIL = "laura@trackflow.test"
PASSWORD = "contraseña-de-alta"
INVITATION = "invitacion-de-pruebas-2026"


def new_user(**overrides) -> UserCreate:
    return UserCreate(**{"email": EMAIL, "password": PASSWORD, **overrides})


def stored_users(auth_env) -> list[dict]:
    return list(json.loads(auth_env.read_text(encoding="utf-8"))["users"].values())


@pytest.fixture
def invitation_required(monkeypatch):
    monkeypatch.setenv("REGISTRATION_CODE", INVITATION)


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_register_creates_an_active_user_with_role_user_and_a_linked_profile():
    result = register(new_user(name="Laura Gómez", phone="+34 976 000 000", address="Zaragoza"))

    assert result.role == Role.USER and result.is_active is True
    assert result.profile.user_id == result.id
    assert (result.profile.name, result.profile.phone, result.profile.address) == (
        "Laura Gómez", "+34 976 000 000", "Zaragoza",
    )
    assert get_user_by_email(EMAIL).id == result.id


def test_password_is_stored_only_as_a_verifiable_bcrypt_hash(auth_env):
    result = register(new_user())

    assert PASSWORD not in auth_env.read_text(encoding="utf-8")
    (user,) = stored_users(auth_env)
    assert user["hashed_password"].startswith("$2b$12$")  # bcrypt, 12 rondas
    assert verify_password(PASSWORD, user["hashed_password"])
    assert not verify_password("otra-contraseña", user["hashed_password"])
    assert "hashed_password" not in result.model_dump()


# --- Casos límite -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [pytest.param("a" * 8, id="8-caracteres"), pytest.param("ñ" * 36, id="72-bytes-con-ñ")],
)
def test_passwords_at_the_length_limits_are_accepted_and_work(password):
    register(new_user(password=password))
    # 72 bytes es el máximo que bcrypt usa entero: la contraseña completa debe seguir verificando.
    assert authenticate(EMAIL, password).email == EMAIL


@pytest.mark.parametrize(
    ("password", "message"),
    [
        pytest.param("a" * 7, "al menos 8 caracteres", id="7-caracteres"),
        pytest.param("ñ" * 36 + "a", "no puede superar 72 bytes", id="73-bytes"),
    ],
)
def test_passwords_just_past_the_limits_are_rejected(password, message):
    with pytest.raises(ValidationError) as error:
        new_user(password=password)
    (problem,) = error.value.errors()
    assert problem["loc"] == ("password",) and message in problem["msg"]


def test_email_is_stored_normalized():
    result = register(new_user(email="  Laura.Gomez@TrackFlow.TEST "))
    assert result.email == "laura.gomez@trackflow.test"
    assert get_user_by_email("laura.gomez@trackflow.test") is not None


def test_blank_profile_fields_are_stored_as_null():
    profile = register(new_user(name="   ", phone="", address=" ")).profile
    assert (profile.name, profile.phone, profile.address) == (None, None, None)


def test_password_keeps_leading_and_trailing_spaces():
    """Defecto D-1 (TESTING.md §11): el registro recortaba los espacios de la contraseña y el login no.

    Quien se registra con «  frase de paso  » debe poder entrar escribiendo exactamente eso.
    """
    password = "  frase de paso con espacios  "
    register(new_user(password=password))
    assert authenticate(EMAIL, password).email == EMAIL


# --- Modos de fallo -----------------------------------------------------------------------------------------------


def test_duplicate_email_is_rejected_even_with_different_case_and_keeps_the_original():
    original = register(new_user())

    with pytest.raises(HTTPException) as error:
        register(new_user(email=" LAURA@TrackFlow.test", password="otra-contraseña-123"))

    assert (error.value.status_code, error.value.detail) == (409, EMAIL_TAKEN)
    assert [user.id for user in list_users()] == [original.id]
    assert verify_password(PASSWORD, get_user_by_email(EMAIL).hashed_password)


@pytest.mark.parametrize(
    "code",
    [None, "", "codigo-que-no-es-el-bueno", INVITATION.upper()],
    ids=["sin-codigo", "vacio", "incorrecto", "otras-mayusculas"],
)
def test_wrong_or_missing_invitation_code_is_rejected_without_creating_anything(invitation_required, code):
    with pytest.raises(HTTPException) as error:
        register(new_user(invitation_code=code))
    assert (error.value.status_code, error.value.detail) == (403, INVALID_INVITATION)
    assert list_users() == []


def test_invitation_code_is_checked_before_the_duplicate_email(invitation_required):
    register(new_user(invitation_code=INVITATION))
    # Sin el código, un 409 confirmaría que el email está registrado.
    with pytest.raises(HTTPException) as error:
        register(new_user(invitation_code="codigo-que-no-es-el-bueno"))
    assert error.value.status_code == 403


def test_valid_invitation_code_registers_and_is_never_stored(invitation_required, auth_env):
    result = register(new_user(invitation_code=INVITATION))
    assert result.role == Role.USER
    assert INVITATION not in auth_env.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "extra",
    [{"role": "admin"}, {"role": "manager"}, {"is_active": False}, {"id": "id-elegido"}],
    ids=["role-admin", "role-manager", "is-active", "id"],
)
def test_registration_cannot_choose_role_state_or_id(extra):
    with pytest.raises(ValidationError) as error:
        new_user(**extra)
    assert {problem["type"] for problem in error.value.errors()} == {"extra_forbidden"}
