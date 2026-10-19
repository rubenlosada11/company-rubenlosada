"""Comprobaciones de la infraestructura de `tests/auth/conftest.py`.

No prueban la aplicación: garantizan que el reloj fijo controla de verdad la emisión y la validación (si una versión
nueva de python-jose dejara de leer `datetime.now`, los tests de caducidad pasarían sin probar nada) y que los tests
no tocan ficheros ni servicios reales.
"""

import urllib.request
from datetime import timedelta

import pytest
from jose import ExpiredSignatureError

from app.database import DEFAULT_AUTH_DB_PATH, get_auth_db_path
from app.security import create_access_token, decode_access_token
from app.services import password_reset as password_reset_service

from .conftest import T0


def test_clock_controls_token_issue_time(clock, ana):
    token, _ = create_access_token(ana.id, timedelta(seconds=10))
    claims = decode_access_token(token)
    assert claims["iat"] == int(T0.timestamp())
    assert claims["exp"] == int(T0.timestamp()) + 10


def test_clock_controls_jose_expiration_check(clock, ana):
    # Las dos mitades hacen falta: con el reloj real, T0 + 10 s ya pasó y solo la segunda seguiría pasando.
    token, _ = create_access_token(ana.id, timedelta(seconds=10))
    clock.advance(seconds=9)
    assert decode_access_token(token)["sub"] == ana.id
    clock.advance(seconds=2)
    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token)


def test_clock_controls_user_and_reset_link_timestamps(clock, ana):
    assert ana.created_at == T0
    issued = password_reset_service.issue_reset_token(ana.id)
    assert issued.expires_at == T0 + timedelta(minutes=30)


def test_auth_database_is_a_temporary_file(auth_env, tmp_path):
    assert get_auth_db_path() == auth_env
    assert auth_env.is_relative_to(tmp_path)
    assert get_auth_db_path() != DEFAULT_AUTH_DB_PATH


def test_network_is_blocked():
    with pytest.raises(AssertionError, match="conexión de red"):
        urllib.request.urlopen("https://api.resend.com/emails")
