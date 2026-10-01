"""Dependencias de autenticación: `get_current_user` y el esquema Bearer de `/docs`.

Cualquier fallo de autenticación responde 401 con `WWW-Authenticate: Bearer`, también un token emitido antes del
último cambio de contraseña del usuario. Los fallos de permisos (usuario autenticado que actúa sobre algo ajeno) son
403 y los decide cada router.
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
    if not issued_after_password_change(claims.get("iat"), user):
        raise unauthorized(INVALID_TOKEN)
    return user


def issued_after_password_change(issued_at: object, user: User) -> bool:
    """`False` si el token se emitió antes del último cambio o restablecimiento de contraseña (AUTH-03).

    Así, cambiar la contraseña cierra todas las sesiones abiertas, también la de quien hubiera robado un token. `iat`
    va en segundos enteros: un token emitido en el mismo segundo que el cambio sigue valiendo (margen de 1 s).
    """
    if user.password_changed_at is None:
        return True
    if isinstance(issued_at, bool) or not isinstance(issued_at, int | float):
        return False
    return issued_at >= int(user.password_changed_at.timestamp())


CurrentUser = Annotated[User, Depends(get_current_user)]
