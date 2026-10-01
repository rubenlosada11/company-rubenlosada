"""Login, usuario actual y recuperación de contraseña (`/auth`).

Autenticación sin estado: JWT Bearer, sin sesiones ni cookies. La recuperación de contraseña (AUTH-03) usa enlaces
de un solo uso guardados en TinyDB (`app/services/password_reset.py`) y enviados por email (`app/services/email.py`).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth_models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ProfilePublic,
    ResetPasswordRequest,
    Token,
    User,
    UserWithProfile,
    normalize_email,
)
from app.dependencies import INVALID_TOKEN, CurrentUser, unauthorized
from app.email_templates import password_reset_email
from app.security import (
    burn_password_check,
    create_access_token,
    get_reset_token_expire_minutes,
    hash_password,
    password_reset_url,
    verify_password,
)
from app.services import password_reset as password_reset_service
from app.services import users as users_service
from app.services.email import EmailSender, deliver, get_email_sender
from app.services.profiles import get_or_create_profile
from app.services.users import get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Mismo mensaje si el email no existe o la contraseña no coincide: no se revela qué emails están registrados.
BAD_CREDENTIALS = "Email o contraseña incorrectos."
INACTIVE_ACCOUNT = "La cuenta está desactivada. Contacta con un administrador."

# Misma respuesta exista o no el email (requisito de AUTH-03: no revelar qué emails están registrados).
FORGOT_PASSWORD_MESSAGE = "Si esa dirección está registrada, recibirás un enlace para restablecer tu contraseña."
# Un único mensaje para cualquier enlace no válido (inexistente, manipulado, caducado o ya usado): no da pistas.
INVALID_RESET_LINK = "El enlace para restablecer la contraseña no es válido o ha caducado. Solicita uno nuevo."
PASSWORD_RESET_DONE = "Contraseña actualizada. Ya puedes iniciar sesión con la nueva contraseña."
# 400 y no 401: la sesión es válida; lo incorrecto es un dato del formulario (el frontend no debe cerrar la sesión).
WRONG_CURRENT_PASSWORD = "La contraseña actual no es correcta."

LOGIN_RESPONSES = {
    401: {"description": "Email o contraseña incorrectos"},
    403: {"description": "Credenciales correctas, pero la cuenta está desactivada"},
}


def authenticate(email: str, password: str) -> User:
    user = get_user_by_email(email)
    if user is None:
        burn_password_check(password)
        raise unauthorized(BAD_CREDENTIALS)
    if not verify_password(password, user.hashed_password):
        raise unauthorized(BAD_CREDENTIALS)
    # Solo se informa de la desactivación a quien ya ha demostrado conocer la contraseña.
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=INACTIVE_ACCOUNT)
    return user


def issue_token(user: User) -> Token:
    access_token, expires_in = create_access_token(user.id)
    return Token(access_token=access_token, expires_in=expires_in)


@router.post("/login", responses=LOGIN_RESPONSES)
def login(payload: LoginRequest) -> Token:
    """Login con JSON `{"email", "password"}`. Devuelve el Bearer token para la cabecera `Authorization`."""
    return issue_token(authenticate(payload.email, payload.password))


@router.post("/token", responses=LOGIN_RESPONSES)
def login_form(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    """Mismo login en formato de formulario OAuth2 (`username` = email). Lo usa el botón «Authorize» de `/docs`."""
    return issue_token(authenticate(normalize_email(form.username), form.password))


@router.get("/me")
def me(current_user: CurrentUser) -> UserWithProfile:
    """Email, rol y perfil del usuario autenticado."""
    profile = get_or_create_profile(current_user.id)
    return UserWithProfile(
        **current_user.model_dump(exclude={"hashed_password"}),
        profile=ProfilePublic.model_validate(profile.model_dump()),
    )


@router.post("/forgot-password", responses={422: {"description": "El email no tiene un formato válido"}})
def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> MessageResponse:
    """Pide un enlace para restablecer la contraseña. Responde **siempre** 200 con el mismo mensaje.

    Solo si el email es de un usuario activo (y no pidió otro enlace hace menos de 60 s) se crea un enlace de un solo
    uso y se envía por email. El envío ocurre **después** de responder (`BackgroundTasks`): así el tiempo de
    respuesta no delata si el email existe, y un fallo del proveedor no cambia la respuesta (queda en el log).
    """
    user = get_user_by_email(payload.email)
    if user is not None and user.is_active:
        issued = password_reset_service.issue_reset_token(user.id)
        if issued is not None:
            message = password_reset_email(
                user.email,
                password_reset_url(issued.token),
                get_reset_token_expire_minutes(),
                idempotency_key=f"password-reset/{issued.id}",
            )
            background_tasks.add_task(deliver, sender, message, purpose="password_reset", user_id=user.id)
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/reset-password",
    responses={
        400: {"description": "El enlace no es válido, ha caducado o ya se usó"},
        422: {"description": "La contraseña nueva no cumple las reglas"},
    },
)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    """Fija una contraseña nueva con el token del enlace del email. El enlace queda usado y no vale una segunda vez.

    Todas las sesiones abiertas del usuario se cierran (sus JWT anteriores responden 401). No inicia sesión: el
    usuario entra después con la contraseña nueva.
    """
    # Comprobación rápida antes de bcrypt (~0,25 s): un token inventado no consume CPU. No es la comprobación que
    # cuenta: `consume_reset_token` la repite de forma atómica, por si otra petición usa el mismo token entretanto.
    if password_reset_service.reset_token_status(payload.token) is not password_reset_service.ResetTokenStatus.VALID:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_RESET_LINK)
    hashed_password = hash_password(payload.new_password)
    try:
        password_reset_service.consume_reset_token(payload.token, hashed_password)
    except password_reset_service.InvalidResetToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_RESET_LINK) from None
    return MessageResponse(message=PASSWORD_RESET_DONE)


@router.post(
    "/change-password",
    responses={
        400: {"description": "La contraseña actual no es correcta"},
        401: {"description": "Sin token o con un token no válido o caducado"},
        422: {"description": "La contraseña nueva no cumple las reglas o es igual a la actual"},
    },
)
def change_password(payload: ChangePasswordRequest, current_user: CurrentUser) -> Token:
    """Cambia la contraseña del usuario autenticado. Exige la contraseña actual.

    Cierra todas las sesiones abiertas (los JWT anteriores responden 401) y anula los enlaces de recuperación
    pendientes. Devuelve un token nuevo para que la sesión desde la que se hace el cambio continúe.
    """
    # Siempre el usuario del token: no hay ningún id en la petición, así que no se puede cambiar la de otro.
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=WRONG_CURRENT_PASSWORD)
    user = users_service.change_password(current_user.id, hash_password(payload.new_password))
    if user is None:  # borrado entre la validación del token y el cambio
        raise unauthorized(INVALID_TOKEN)
    password_reset_service.revoke_reset_tokens(user.id)
    return issue_token(user)
