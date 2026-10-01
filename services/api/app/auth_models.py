"""Modelos de usuarios, perfiles y autenticación.

- `User`: credenciales y estado (email, hash de la contraseña, rol, activo). Sin datos personales.
- `Profile`: datos visibles y de contacto (nombre, teléfono, dirección). Uno por usuario (`user_id`).

- `PasswordResetToken`: enlaces de recuperación de contraseña (AUTH-03), de un solo uso y con caducidad.

Se guardan solo en TinyDB (`app/database.py:auth_db`). Los modelos persistidos (`User`, `Profile`) nunca se
devuelven tal cual: las respuestas usan `UserPublic`, `ProfilePublic` y `MeResponse`, que no tienen `hashed_password`.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import EMAIL_PATTERN


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


# bcrypt solo usa los primeros 72 bytes (y bcrypt 5 rechaza contraseñas más largas): el límite se valida aquí.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72

# Dígitos con prefijo `+` opcional y separadores habituales: "+34 976 000 000", "(213) 555-0100".
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ().-]{5,24}$")

Name = Annotated[str | None, Field(default=None, max_length=100)]
Phone = Annotated[str | None, Field(default=None, max_length=25)]
Address = Annotated[str | None, Field(default=None, max_length=200)]


def normalize_email(value: str) -> str:
    """El email identifica al usuario: se compara sin espacios ni mayúsculas."""
    return value.strip().lower()


def check_email(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    email = normalize_email(value)
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("email no tiene un formato válido")
    return email


def check_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres")
    if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"La contraseña no puede superar {PASSWORD_MAX_BYTES} bytes")
    return value


class ProfileFields(BaseModel):
    """Campos del perfil que controla el usuario. Un texto vacío se guarda como `null`."""

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: Name
    phone: Phone
    address: Address

    @field_validator("name", "phone", "address", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str | None) -> str | None:
        if value is not None and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("phone no tiene un formato de teléfono válido")
        return value


# --- Persistencia (TinyDB) -----------------------------------------------------------------------------------


class User(BaseModel):
    """Usuario tal y como se guarda en TinyDB. `id` es un UUID: es el `sub` del JWT y el `user_uuid` de otros módulos."""

    id: str
    email: str
    hashed_password: str
    is_active: bool
    role: Role
    created_at: datetime
    # Último cambio o restablecimiento de contraseña (UTC). Los JWT emitidos antes dejan de valer. No existe hasta el
    # primer cambio: los usuarios anteriores a AUTH-03 se leen igual.
    password_changed_at: datetime | None = None


class PasswordResetToken(BaseModel):
    """Enlace de recuperación de contraseña (tabla `password_reset_tokens` de TinyDB).

    Solo se guarda el SHA-256 del token: el token en claro únicamente viaja en el email. `used_at` vale `None` mientras
    el enlace no se ha usado.
    """

    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None


class Profile(BaseModel):
    id: str
    user_id: str
    name: str | None = None
    phone: str | None = None
    address: str | None = None


# --- Entrada ---------------------------------------------------------------------------------------------------


class UserCreate(ProfileFields):
    """Registro público (`POST /users`): credenciales + datos iniciales opcionales del perfil.

    No admite `role`, `is_active` ni `id` (`extra: forbid`): todo usuario nuevo es `user` y está activo. Así nadie
    puede registrarse como administrador.

    `invitation_code` solo se comprueba si la API tiene `REGISTRATION_CODE`; nunca se guarda.
    """

    email: str
    password: str
    invitation_code: str | None = Field(default=None, max_length=200)

    _check_email = field_validator("email", mode="before")(check_email)
    _check_password = field_validator("password")(check_password)


class UserUpdate(BaseModel):
    """`PUT /users/{id}`: solo cambian los campos enviados. Quién puede cambiar cada uno lo decide el router.

    No admite `password` (AUTH-03): la contraseña solo se cambia con `POST /auth/change-password`, que exige la actual,
    o con un enlace de recuperación. Cambiar el `email` exige `current_password`: si no, con un token robado se podría
    poner un email propio y pedir un enlace de recuperación para quedarse con la cuenta.
    """

    model_config = {"extra": "forbid"}

    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    # Solo confirma el cambio de email; no es un campo que se modifique.
    current_password: str | None = Field(default=None, max_length=200)

    _check_email = field_validator("email", mode="before")(check_email)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if not self.model_fields_set - {"current_password"}:
            raise ValueError("Envía al menos un campo: email, role o is_active")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null")
        return self


class ProfileUpdate(ProfileFields):
    """`PUT /profiles/me`: solo cambian los campos enviados; `null` o "" vacían el campo."""

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo: name, phone o address")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        # Sin validar el formato: un email mal escrito recibe el mismo 401 que una contraseña incorrecta.
        return normalize_email(value) if isinstance(value, str) else value


class ForgotPasswordRequest(BaseModel):
    """`POST /auth/forgot-password`. Solo se valida el formato: un 422 no dice nada sobre si el email existe."""

    email: str = Field(max_length=254)

    _check_email = field_validator("email", mode="before")(check_email)


class ResetPasswordRequest(BaseModel):
    """`POST /auth/reset-password`: el token del enlace del email y la contraseña nueva (mismas reglas que el alta)."""

    # Los tokens miden 43 caracteres; el límite solo evita cuerpos enormes.
    token: str = Field(max_length=512)
    new_password: str

    _check_password = field_validator("new_password")(check_password)


class ChangePasswordRequest(BaseModel):
    """`POST /auth/change-password` (con sesión): la contraseña actual y la nueva, que debe ser distinta."""

    # Sin reglas de formato: una contraseña actual mal escrita es simplemente incorrecta (400), no un 422.
    current_password: str = Field(max_length=200)
    new_password: str

    _check_password = field_validator("new_password")(check_password)

    @model_validator(mode="after")
    def new_differs_from_current(self) -> "ChangePasswordRequest":
        if self.new_password == self.current_password:
            raise ValueError("La nueva contraseña debe ser distinta de la actual")
        return self


# --- Salida ----------------------------------------------------------------------------------------------------


class UserPublic(BaseModel):
    id: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime


class ProfilePublic(BaseModel):
    id: str
    user_id: str
    name: str | None
    phone: str | None
    address: str | None


class UserWithProfile(UserPublic):
    """Respuesta de `POST /users` y `GET /auth/me`."""

    profile: ProfilePublic


class MessageResponse(BaseModel):
    message: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos hasta que caduca el token")
