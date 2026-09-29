"""Perfil del usuario autenticado (`/profiles/me`).

No hay rutas con `user_id`: el perfil se obtiene siempre del token, así que nadie puede leer ni editar uno ajeno.
"""

from fastapi import APIRouter

from app.auth_models import ProfilePublic, ProfileUpdate
from app.dependencies import CurrentUser
from app.services import profiles as profiles_service

router = APIRouter(prefix="/profiles", tags=["profiles"])

AUTH_RESPONSES = {401: {"description": "Sin token o con un token no válido o caducado"}}


@router.get("/me", responses=AUTH_RESPONSES)
def get_my_profile(current_user: CurrentUser) -> ProfilePublic:
    return ProfilePublic.model_validate(profiles_service.get_or_create_profile(current_user.id).model_dump())


@router.put("/me", responses=AUTH_RESPONSES)
def update_my_profile(payload: ProfileUpdate, current_user: CurrentUser) -> ProfilePublic:
    """Cambia `name`, `phone` y/o `address` (solo los enviados; `null` o "" vacían el campo)."""
    changes = payload.model_dump(exclude_unset=True)
    return ProfilePublic.model_validate(profiles_service.update_profile(current_user.id, changes).model_dump())
