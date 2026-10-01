"""Usuarios (`/users`): registro público y gestión protegida con control de propiedad y rol.

Permisos:

| Operación              | Propio usuario                 | admin                        | manager         | user   |
| ---------------------- | ------------------------------ | ---------------------------- | --------------- | ------ |
| `POST /users`          | público (siempre rol `user`)   |                              |                 |        |
| `GET /users`           | —                              | sí                           | sí              | 403    |
| `GET /users/{id}`      | sí                             | sí                           | sí              | 403    |
| `PUT /users/{id}`      | email (con `current_password`) | `role` e `is_active` de todos | 403 si es ajeno | 403    |
| `DELETE /users/{id}`   | sí (baja propia)               | sí                           | 403 si es ajeno | 403    |

Con `REGISTRATION_CODE` definida, `POST /users` exige además `invitation_code` (403 si falta o no coincide).

La contraseña no se cambia aquí (AUTH-03): `PUT /users/{id}` con `password` responde 422. Se cambia con
`POST /auth/change-password` (exige la actual) o con un enlace de `POST /auth/forgot-password`. Cambiar el email exige
`current_password` (400 si falta o no es correcta) y anula los enlaces de recuperación pendientes.

Los permisos se comprueban antes que la existencia: quien no puede ver otros usuarios recibe 403 también con un id
inexistente, y así no puede averiguar qué ids existen.
"""

from fastapi import APIRouter, HTTPException, status

from app.auth_models import ProfilePublic, Role, User, UserCreate, UserPublic, UserUpdate, UserWithProfile
from app.dependencies import CurrentUser
from app.security import invitation_code_is_valid, verify_password
from app.services import password_reset as password_reset_service
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

# Quién puede consultar usuarios ajenos.
STAFF_ROLES = {Role.ADMIN, Role.MANAGER}
# Campos que solo cambia un administrador y campos (credenciales) que solo cambia su propietario.
ADMIN_FIELDS = {"role", "is_active"}
CREDENTIAL_FIELDS = {"email"}

USER_NOT_FOUND = "Usuario no encontrado."
EMAIL_TAKEN = "Ya existe un usuario con ese email."
INVALID_INVITATION = "Código de invitación no válido."
EMAIL_NEEDS_PASSWORD = "Para cambiar el email, indica tu contraseña actual (current_password)."
WRONG_CURRENT_PASSWORD = "La contraseña actual no es correcta."

AUTH_RESPONSES = {
    401: {"description": "Sin token o con un token no válido o caducado"},
    403: {"description": "Autenticado, pero sin permiso sobre este usuario"},
    404: {"description": "Usuario no encontrado"},
}


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=detail)


def to_public(user: User) -> UserPublic:
    return UserPublic.model_validate(user.model_dump(exclude={"hashed_password"}))


def get_or_404(user_id: str) -> User:
    user = users_service.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return user


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Falta el código de invitación o no es válido (solo con `REGISTRATION_CODE`)"},
        409: {"description": EMAIL_TAKEN},
    },
)
def register(payload: UserCreate) -> UserWithProfile:
    """Registro público. Crea el usuario (rol `user`, activo) y su perfil con `name`, `phone` y `address` opcionales.

    Si la API tiene `REGISTRATION_CODE`, exige `invitation_code`. Se comprueba antes que el email: sin el código no se
    puede averiguar qué emails están registrados.
    """
    if not invitation_code_is_valid(payload.invitation_code):
        raise forbidden(INVALID_INVITATION)
    try:
        user, profile = users_service.create_user(payload)
    except users_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    return UserWithProfile(**to_public(user).model_dump(), profile=ProfilePublic.model_validate(profile.model_dump()))


@router.get("", responses=AUTH_RESPONSES)
def list_users(current_user: CurrentUser) -> list[UserPublic]:
    """Todos los usuarios, sin hashes de contraseña. Solo `admin` y `manager`."""
    if current_user.role not in STAFF_ROLES:
        raise forbidden("Solo un administrador o un manager puede listar usuarios.")
    return [to_public(user) for user in users_service.list_users()]


@router.get("/{user_id}", responses=AUTH_RESPONSES)
def get_user(user_id: str, current_user: CurrentUser) -> UserPublic:
    if user_id != current_user.id and current_user.role not in STAFF_ROLES:
        raise forbidden("No puedes consultar otros usuarios.")
    return to_public(get_or_404(user_id))


@router.put(
    "/{user_id}",
    responses={
        **AUTH_RESPONSES,
        400: {"description": "Cambio de email sin `current_password` o con una incorrecta"},
        409: {"description": EMAIL_TAKEN},
    },
)
def update_user(user_id: str, payload: UserUpdate, current_user: CurrentUser) -> UserPublic:
    """Cambia solo los campos enviados. Email: el propio usuario, con `current_password`. Rol y estado: un `admin`.

    La contraseña no: `POST /auth/change-password` (con la actual) o la recuperación por email.
    """
    changes = payload.model_dump(exclude_unset=True)
    current_password = changes.pop("current_password", None)
    is_owner = user_id == current_user.id
    is_admin = current_user.role == Role.ADMIN

    if not is_owner and not is_admin:
        raise forbidden("No puedes modificar otros usuarios.")
    if ADMIN_FIELDS & changes.keys() and not is_admin:
        raise forbidden("Solo un administrador puede cambiar el rol o el estado de un usuario.")
    if CREDENTIAL_FIELDS & changes.keys() and not is_owner:
        raise forbidden("Solo el propio usuario puede cambiar su email.")
    # Quien cambia el email recibe los enlaces de recuperación: un token robado no debe bastar (AUTH-03).
    if "email" in changes:
        if current_password is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=EMAIL_NEEDS_PASSWORD)
        if not verify_password(current_password, current_user.hashed_password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=WRONG_CURRENT_PASSWORD)

    try:
        user = users_service.update_user(user_id, changes)
    except users_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    if "email" in changes:
        # Los enlaces pendientes se enviaron al email anterior: dejan de valer.
        password_reset_service.revoke_reset_tokens(user.id)
    return to_public(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=AUTH_RESPONSES)
def delete_user(user_id: str, current_user: CurrentUser) -> None:
    """Borra el usuario y su perfil. El propio usuario (baja) o un `admin`."""
    if user_id != current_user.id and current_user.role != Role.ADMIN:
        raise forbidden("No puedes eliminar otros usuarios.")
    if not users_service.delete_user(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
