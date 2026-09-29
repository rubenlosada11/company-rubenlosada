"""Contraseñas (bcrypt) y tokens de acceso (JWT firmado con HS256).

Configuración por variables de entorno (ver `.env.example`), leída en cada uso para que los tests puedan cambiarla:

- `SECRET_KEY` (obligatoria): clave de firma de los JWT, de al menos 32 caracteres.
- `ACCESS_TOKEN_EXPIRE_MINUTES` (opcional, 30 por defecto): validez de cada token.
"""

import os
from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 30
SECRET_KEY_MIN_LENGTH = 32
PLACEHOLDER_SECRET = "change-me"

# `libpass` (fork mantenido de passlib) instala el módulo `passlib`; el esquema es bcrypt con 12 rondas.
_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash de una contraseña que nadie conoce: el login lo verifica cuando el email no existe, para tardar lo mismo que
# con una contraseña incorrecta y no revelar qué emails están registrados.
_DUMMY_HASH = _password_context.hash("trackflow-usuario-inexistente")


class ConfigError(RuntimeError):
    """Configuración de autenticación ausente o insegura."""


def get_secret_key() -> str:
    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret or secret == PLACEHOLDER_SECRET:
        raise ConfigError(
            "SECRET_KEY no está configurada o tiene el valor de ejemplo. Crea services/api/.env a partir de "
            ".env.example y genera una clave con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if len(secret) < SECRET_KEY_MIN_LENGTH:
        raise ConfigError(f"SECRET_KEY debe tener al menos {SECRET_KEY_MIN_LENGTH} caracteres.")
    return secret


def get_access_token_expire_minutes() -> int:
    raw = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
    if not raw:
        return DEFAULT_EXPIRE_MINUTES
    try:
        minutes = int(raw)
    except ValueError:
        raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser un número entero de minutos.") from None
    if minutes <= 0:
        raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser mayor que 0.")
    return minutes


def check_auth_config() -> None:
    """Falla al arrancar la API si la configuración no es válida, en lugar de en el primer login."""
    get_secret_key()
    get_access_token_expire_minutes()


def hash_password(password: str) -> str:
    return _password_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    # bcrypt 5 lanza ValueError con más de 72 bytes; ninguna contraseña guardada puede ser tan larga (se valida
    # al crearla), así que es simplemente incorrecta. Se comprueba un recorte para tardar lo mismo.
    if len(password.encode("utf-8")) > 72:
        _password_context.verify(password.encode("utf-8")[:72], hashed_password)
        return False
    return _password_context.verify(password, hashed_password)


def burn_password_check(password: str) -> None:
    """Verificación sin resultado, para igualar el tiempo de respuesta cuando el usuario no existe."""
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: str, expires_delta: timedelta | None = None) -> tuple[str, int]:
    """JWT con `sub` = id del usuario en TinyDB, `iat` y `exp`. Devuelve el token y su validez en segundos."""
    lifetime = expires_delta if expires_delta is not None else timedelta(minutes=get_access_token_expire_minutes())
    now = datetime.now(UTC)
    claims = {"sub": user_id, "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, get_secret_key(), algorithm=ALGORITHM), int(lifetime.total_seconds())


def decode_access_token(token: str) -> dict:
    """Verifica firma, algoritmo y caducidad, y exige `sub` y `exp`.

    Lanza `jose.ExpiredSignatureError` si ha caducado y `jose.JWTError` en cualquier otro caso.
    """
    return jwt.decode(
        token,
        get_secret_key(),
        algorithms=[ALGORITHM],
        options={"require_exp": True, "require_sub": True},
    )
