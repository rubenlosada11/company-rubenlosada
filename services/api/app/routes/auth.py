"""Login y usuario actual (`/auth`). Autenticación sin estado: JWT Bearer, sin sesiones ni cookies."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth_models import LoginRequest, ProfilePublic, Token, User, UserWithProfile, normalize_email
from app.dependencies import CurrentUser, unauthorized
from app.security import burn_password_check, create_access_token, verify_password
from app.services.profiles import get_or_create_profile
from app.services.users import get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Mismo mensaje si el email no existe o la contraseña no coincide: no se revela qué emails están registrados.
BAD_CREDENTIALS = "Email o contraseña incorrectos."
INACTIVE_ACCOUNT = "La cuenta está desactivada. Contacta con un administrador."

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
