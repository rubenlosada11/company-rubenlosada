"""Contraseñas (bcrypt) y tokens de acceso (JWT firmado con HS256).

Configuración por variables de entorno (ver `.env.example`), leída en cada uso para que los tests puedan cambiarla:

- `SECRET_KEY` (obligatoria): clave de firma de los JWT, de al menos 32 caracteres.
- `ACCESS_TOKEN_EXPIRE_MINUTES` (opcional, 30 por defecto): validez de cada token.
- `REGISTRATION_CODE` (opcional): si está definida, `POST /users` exige `invitation_code` igual a este valor. Sin ella,
  el registro es abierto (desarrollo local).
- `RESET_TOKEN_EXPIRE_MINUTES` (opcional, 30 por defecto, entre 15 y 60): validez de los enlaces de recuperación de
  contraseña.
- `FRONTEND_BASE_URL` (opcional, `http://localhost:3002` por defecto): URL pública del backoffice, a la que apunta el
  enlace del email (`<FRONTEND_BASE_URL>/reset-password?token=…`).

La configuración del envío de emails (`RESEND_API_KEY`, `MAIL_FROM`) está en `app/services/email.py`.
"""

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

from jose import jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 30
SECRET_KEY_MIN_LENGTH = 32
PLACEHOLDER_SECRET = "change-me"
REGISTRATION_CODE_MIN_LENGTH = 12
DEFAULT_RESET_TOKEN_EXPIRE_MINUTES = 30
# Ventana del ticket (AUTH-03): lo bastante larga para abrir el email y lo bastante corta para limitar un enlace robado.
RESET_TOKEN_EXPIRE_RANGE = (15, 60)
# 32 bytes aleatorios = 256 bits: imposible de adivinar, así que basta un SHA-256 (sin sal) para guardarlo.
RESET_TOKEN_BYTES = 32
DEFAULT_FRONTEND_BASE_URL = "http://localhost:3002"
RESET_PASSWORD_PATH = "/reset-password"

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


def get_registration_code() -> str | None:
    """Código de invitación exigido para registrarse, o `None` si el registro es abierto."""
    code = os.environ.get("REGISTRATION_CODE", "").strip()
    if not code:
        return None
    # Sin límite de intentos, un código corto se adivina por fuerza bruta.
    if len(code) < REGISTRATION_CODE_MIN_LENGTH:
        raise ConfigError(f"REGISTRATION_CODE debe tener al menos {REGISTRATION_CODE_MIN_LENGTH} caracteres.")
    return code


def invitation_code_is_valid(candidate: str | None) -> bool:
    """`True` si el registro es abierto o si `candidate` coincide con `REGISTRATION_CODE` (en tiempo constante)."""
    expected = get_registration_code()
    if expected is None:
        return True
    # En bytes: `compare_digest` no admite `str` con caracteres que no sean ASCII.
    return hmac.compare_digest((candidate or "").encode("utf-8"), expected.encode("utf-8"))


def get_reset_token_expire_minutes() -> int:
    raw = os.environ.get("RESET_TOKEN_EXPIRE_MINUTES", "").strip()
    if not raw:
        return DEFAULT_RESET_TOKEN_EXPIRE_MINUTES
    low, high = RESET_TOKEN_EXPIRE_RANGE
    try:
        minutes = int(raw)
    except ValueError:
        raise ConfigError("RESET_TOKEN_EXPIRE_MINUTES debe ser un número entero de minutos.") from None
    if not low <= minutes <= high:
        raise ConfigError(f"RESET_TOKEN_EXPIRE_MINUTES debe estar entre {low} y {high} minutos.")
    return minutes


def get_frontend_base_url() -> str:
    """URL pública del backoffice, sin barra final. Debe ser una URL `http(s)://` absoluta: va en los emails."""
    raw = os.environ.get("FRONTEND_BASE_URL", "").strip() or DEFAULT_FRONTEND_BASE_URL
    url = raw.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
        raise ConfigError(
            "FRONTEND_BASE_URL debe ser la URL pública del backoffice, p. ej. https://backoffice.ejemplo.com "
            "(con http:// o https:// y sin parámetros)."
        )
    return url


def password_reset_url(token: str) -> str:
    """Enlace del email de recuperación: `<FRONTEND_BASE_URL>/reset-password?token=<token>`."""
    return f"{get_frontend_base_url()}{RESET_PASSWORD_PATH}?{urlencode({'token': token})}"


def check_auth_config() -> None:
    """Falla al arrancar la API si la configuración no es válida, en lugar de en el primer login."""
    get_secret_key()
    get_access_token_expire_minutes()
    get_registration_code()
    get_reset_token_expire_minutes()
    get_frontend_base_url()


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


def generate_reset_token() -> str:
    """Token opaco de recuperación de contraseña (URL-safe). Solo viaja en el email; nunca se guarda en claro."""
    return secrets.token_urlsafe(RESET_TOKEN_BYTES)


def hash_reset_token(token: str) -> str:
    """SHA-256 del token, que es lo único que se guarda: con la base de datos no se puede reconstruir el enlace."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
