"""Dependencias de autenticación: `get_current_user` y el esquema Bearer de `/docs`.

Cualquier fallo de autenticación responde 401 con `WWW-Authenticate: Bearer`. Los fallos de permisos (usuario
autenticado que actúa sobre algo ajeno) son 403 y los decide cada router.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError

from app.auth_models import User
from app.security import decode_access_token
from app.services.users import get_user

# `tokenUrl` es el endpoint de formulario OAuth2 que usa el botón «Authorize» de Swagger UI.
# `auto_error=False`: el 401 por token ausente se lanza abajo, con el mismo formato que el resto.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="auth/token",
    auto_error=False,
    description="En «Authorize», usa tu email como *username* y tu contraseña.",
)

NOT_AUTHENTICATED = "No autenticado. Inicia sesión y envía el token en la cabecera Authorization: Bearer <token>."
INVALID_TOKEN = "Token no válido."
EXPIRED_TOKEN = "El token ha caducado. Inicia sesión de nuevo."


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    """Valida el Bearer token (firma, caducidad, `sub`) y devuelve el usuario activo de TinyDB."""
    if not token:
        raise unauthorized(NOT_AUTHENTICATED)
    try:
        claims = decode_access_token(token)
    except ExpiredSignatureError:
        raise unauthorized(EXPIRED_TOKEN) from None
    except JWTError:
        raise unauthorized(INVALID_TOKEN) from None

    user_id = claims.get("sub")
    user = get_user(user_id) if isinstance(user_id, str) and user_id else None
    # Usuario borrado o desactivado después de emitir el token: el token deja de servir.
    if user is None or not user.is_active:
        raise unauthorized(INVALID_TOKEN)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
