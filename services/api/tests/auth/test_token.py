"""Validación del Bearer token: la dependencia de todas las rutas protegidas (AUTH-088, TESTING.md §6, fila 4).

Se llama a `get_current_user(token)` (la dependencia real, sin HTTP) y a las funciones de `app/security.py`. Los
tokens se firman con la `SECRET_KEY` de pruebas de `tests/conftest.py`; los manipulados se construyen aquí. El reloj
está congelado (`clock`) para fijar los instantes de caducidad sin esperas reales.
"""

import base64
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from app.dependencies import EXPIRED_TOKEN, INVALID_TOKEN, NOT_AUTHENTICATED, get_current_user
from app.security import ALGORITHM, ConfigError, create_access_token, get_access_token_expire_minutes, get_secret_key
from app.services import users as users_service
from conftest import TEST_SECRET_KEY

from .conftest import T0

NOW = int(T0.timestamp())
OTHER_KEY = "otra-clave-de-pruebas-con-mas-de-32-caracteres"


def sign(claims: dict, key: str = TEST_SECRET_KEY, algorithm: str = ALGORITHM) -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def claims_for(user, **overrides) -> dict:
    """Claims de un token emitido en T0 y válido 30 min; `None` en un override elimina el claim."""
    claims = {"sub": user.id, "iat": NOW, "exp": NOW + 1800, **overrides}
    return {name: value for name, value in claims.items() if value is not None}


def unsigned(claims: dict) -> str:
    """Token con `alg: none` y sin firma (python-jose no permite generarlo)."""

    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


def rejected(token: str | None) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        get_current_user(token)
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    return error.value


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_fresh_token_gives_the_active_user(clock, ana):
    token, expires_in = create_access_token(ana.id)
    assert get_current_user(token).id == ana.id
    assert expires_in == 1800


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_token_expires_exactly_at_its_exp_instant(clock, ana):
    """Caso sugerido en la revisión asistida por IA (TESTING.md §8, defecto D-2).

    RFC 7519 §4.1.4: la hora actual debe ser **anterior** a `exp`. python-jose solo rechaza `exp < ahora`, así que sin
    la corrección el token seguía valiendo durante el segundo exacto de `exp`.
    """
    token, _ = create_access_token(ana.id, timedelta(seconds=60))

    clock.set(T0 + timedelta(seconds=59, microseconds=999_999))
    assert get_current_user(token).id == ana.id

    clock.set(T0 + timedelta(seconds=60))
    assert rejected(token).detail == EXPIRED_TOKEN

    clock.set(T0 + timedelta(seconds=61))
    assert rejected(token).detail == EXPIRED_TOKEN


@pytest.mark.parametrize(("exp", "valid"), [(str(NOW + 60), True), (str(NOW), False)], ids=["futuro", "ahora"])
def test_exp_written_as_text_is_compared_as_a_number(clock, ana, exp, valid):
    # python-jose acepta un `exp` que `int()` pueda convertir; la comprobación del instante exacto no debe dar un 500.
    token = sign(claims_for(ana, exp=exp))
    if valid:
        assert get_current_user(token).id == ana.id
    else:
        assert rejected(token).detail == EXPIRED_TOKEN


def test_token_issued_in_the_same_second_as_a_password_change_still_works(clock, ana):
    token, _ = create_access_token(ana.id)  # iat = T0
    clock.advance(microseconds=700_000)
    users_service.change_password(ana.id, ana.hashed_password)  # password_changed_at = T0 + 0,7 s
    # `iat` va en segundos enteros: el token de la sesión que hizo el cambio no debe morir por redondeo.
    assert get_current_user(token).id == ana.id


def test_token_issued_one_second_before_a_password_change_is_revoked(clock, ana):
    token, _ = create_access_token(ana.id)  # iat = T0
    clock.advance(seconds=1)
    users_service.change_password(ana.id, ana.hashed_password)
    assert rejected(token).detail == INVALID_TOKEN


def test_token_lifetime_follows_access_token_expire_minutes(clock, ana, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1")
    token, expires_in = create_access_token(ana.id)
    assert expires_in == 60
    clock.advance(seconds=60)
    assert rejected(token).detail == EXPIRED_TOKEN


def test_secret_key_of_exactly_32_characters_is_accepted(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    assert get_secret_key() == "k" * 32


# --- Modos de fallo: token ausente, ilegible o no firmado por la API ----------------------------------------------


@pytest.mark.parametrize("token", [None, ""], ids=["sin-cabecera", "vacio"])
def test_missing_token_is_not_authenticated(token):
    assert rejected(token).detail == NOT_AUTHENTICATED


@pytest.mark.parametrize("token", ["no-es-un-jwt", "a.b.c", "Bearer x.y.z"], ids=["texto", "tres-partes", "con-prefijo"])
def test_malformed_token_is_invalid(token):
    assert rejected(token).detail == INVALID_TOKEN


def test_token_signed_with_another_key_is_invalid(clock, ana):
    assert rejected(sign(claims_for(ana), key=OTHER_KEY)).detail == INVALID_TOKEN


def test_token_without_signature_alg_none_is_invalid(clock, ana):
    assert rejected(unsigned(claims_for(ana))).detail == INVALID_TOKEN


def test_token_signed_with_a_different_algorithm_is_invalid(clock, ana):
    # Misma clave, otro algoritmo: la API solo admite HS256.
    assert rejected(sign(claims_for(ana), algorithm="HS512")).detail == INVALID_TOKEN


def test_expired_token_has_its_own_message(clock, ana):
    token = sign(claims_for(ana, iat=NOW - 3600, exp=NOW - 1))
    assert rejected(token).detail == EXPIRED_TOKEN


# --- Modos de fallo: claims ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["sub", "exp"])
def test_token_without_a_required_claim_is_invalid(clock, ana, missing):
    assert rejected(sign(claims_for(ana, **{missing: None}))).detail == INVALID_TOKEN


@pytest.mark.parametrize("sub", ["", 12345], ids=["vacio", "numero"])
def test_token_with_an_unusable_subject_is_invalid(clock, ana, sub):
    assert rejected(sign(claims_for(ana, sub=sub))).detail == INVALID_TOKEN


def test_token_for_an_id_that_does_not_exist_is_invalid(clock):
    assert rejected(sign({"sub": "00000000-0000-0000-0000-000000000000", "iat": NOW, "exp": NOW + 60})).detail == (
        INVALID_TOKEN
    )


@pytest.mark.parametrize("iat", [None, True], ids=["sin-iat", "iat-booleano"])
def test_after_a_password_change_a_token_needs_a_numeric_iat(clock, ana, iat):
    users_service.change_password(ana.id, ana.hashed_password)
    assert rejected(sign(claims_for(ana, iat=iat))).detail == INVALID_TOKEN


def test_token_without_iat_is_accepted_while_the_password_never_changed(clock, ana):
    # Contrato vigente: `iat` solo se exige para comparar con un cambio de contraseña.
    assert get_current_user(sign(claims_for(ana, iat=None))).id == ana.id


# --- Modos de fallo: el usuario ya no puede usar la sesión --------------------------------------------------------


def test_token_of_a_deactivated_user_is_invalid(clock, ana):
    token, _ = create_access_token(ana.id)
    users_service.update_user(ana.id, {"is_active": False})
    assert rejected(token).detail == INVALID_TOKEN


def test_token_of_a_deleted_user_is_invalid(clock, ana):
    token, _ = create_access_token(ana.id)
    users_service.delete_user(ana.id)
    assert rejected(token).detail == INVALID_TOKEN


# --- Modos de fallo: configuración insegura -----------------------------------------------------------------------


@pytest.mark.parametrize("secret", ["", "   ", "change-me", "k" * 31], ids=["vacia", "espacios", "ejemplo", "31-caracteres"])
def test_missing_or_weak_secret_key_stops_token_issue_and_validation(monkeypatch, ana, secret):
    token, _ = create_access_token(ana.id)
    monkeypatch.setenv("SECRET_KEY", secret)
    with pytest.raises(ConfigError):
        create_access_token(ana.id)
    with pytest.raises(ConfigError):
        get_current_user(token)


@pytest.mark.parametrize("minutes", ["0", "-5", "media-hora", "1.5"])
def test_invalid_token_lifetime_is_a_config_error(monkeypatch, minutes):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", minutes)
    with pytest.raises(ConfigError):
        get_access_token_expire_minutes()
