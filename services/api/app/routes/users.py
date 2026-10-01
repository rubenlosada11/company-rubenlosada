"""Usuarios (`/users`): registro público y gestión protegida con control de propiedad y rol.

Permisos:

| Operación              | Propio usuario                 | admin                        | manager         | user   |
| ---------------------- | ------------------------------ | ---------------------------- | --------------- | ------ |
| `POST /users`          | público (siempre rol `user`)   |                              |                 |        |
| `GET /users`           | —                              | sí                           | sí              | 403    |
| `GET /users/{id}`      | sí                             | sí                           | sí              | 403    |
| `PUT /users/{id}`      | email y contraseña             | `role` e `is_active` de todos | 403 si es ajeno | 403    |
| `DELETE /users/{id}`   | sí (baja propia)               | sí                           | 403 si es ajeno | 403    |

Con `REGISTRATION_CODE` definida, `POST /users` exige además `invitation_code` (403 si falta o no coincide).

Los permisos se comprueban antes que la existencia: quien no puede ver otros usuarios recibe 403 también con un id
inexistente, y así no puede averiguar qué ids existen.
"""

from fastapi import APIRouter, HTTPException, status

from app.auth_models import ProfilePublic, Role, User, UserCreate, UserPublic, UserUpdate, UserWithProfile
from app.dependencies import CurrentUser
from app.security import invitation_code_is_valid
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

# Quién puede consultar usuarios ajenos.
STAFF_ROLES = {Role.ADMIN, Role.MANAGER}
# Campos que solo cambia un administrador y campos (credenciales) que solo cambia su propietario.
ADMIN_FIELDS = {"role", "is_active"}
CREDENTIAL_FIELDS = {"email", "password"}

USER_NOT_FOUND = "Usuario no encontrado."
EMAIL_TAKEN = "Ya existe un usuario con ese email."
INVALID_INVITATION = "Código de invitación no válido."

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


@router.put("/{user_id}", responses={**AUTH_RESPONSES, 409: {"description": EMAIL_TAKEN}})
def update_user(user_id: str, payload: UserUpdate, current_user: CurrentUser) -> UserPublic:
    """Cambia solo los campos enviados. Email y contraseña: el propio usuario. Rol y estado: un `admin`."""
    changes = payload.model_dump(exclude_unset=True)
    is_owner = user_id == current_user.id
    is_admin = current_user.role == Role.ADMIN

    if not is_owner and not is_admin:
        raise forbidden("No puedes modificar otros usuarios.")
    if ADMIN_FIELDS & changes.keys() and not is_admin:
        raise forbidden("Solo un administrador puede cambiar el rol o el estado de un usuario.")
    if CREDENTIAL_FIELDS & changes.keys() and not is_owner:
        raise forbidden("Solo el propio usuario puede cambiar su email o su contraseña.")

    try:
        user = users_service.update_user(user_id, changes)
    except users_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return to_public(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=AUTH_RESPONSES)
def delete_user(user_id: str, current_user: CurrentUser) -> None:
    """Borra el usuario y su perfil. El propio usuario (baja) o un `admin`."""
    if user_id != current_user.id and current_user.role != Role.ADMIN:
        raise forbidden("No puedes eliminar otros usuarios.")
    if not users_service.delete_user(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
