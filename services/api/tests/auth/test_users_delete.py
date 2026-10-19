"""`DELETE /users/{id}` — baja propia o por un admin (AUTH-088, TESTING.md §6, fila 12).

Se llama a la función del router con el usuario de la dependencia real. Se comprueba el efecto en la base (usuario y
perfil) y que la sesión del usuario borrado deja de valer.
"""

import json

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.routes import users as users_routes
from app.routes.users import USER_NOT_FOUND
from app.security import create_access_token
from app.services import users as users_service

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def as_user(user):
    token, _ = create_access_token(user.id)
    return get_current_user(token)


def stored_ids(auth_env, table: str, field: str) -> list[str]:
    return [doc[field] for doc in json.loads(auth_env.read_text(encoding="utf-8")).get(table, {}).values()]


def failure(target_id: str, actor) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        users_routes.delete_user(target_id, as_user(actor))
    return error.value


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_user_deletes_own_account_profile_included_and_the_session_dies(ana, auth_env):
    token, _ = create_access_token(ana.id)
    users_routes.delete_user(ana.id, get_current_user(token))

    assert ana.id not in stored_ids(auth_env, "users", "id")
    assert ana.id not in stored_ids(auth_env, "profiles", "user_id")
    with pytest.raises(HTTPException) as error:
        get_current_user(token)
    assert error.value.status_code == 401


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_admin_deletes_another_user_and_a_second_delete_is_404(admin, ana, auth_env):
    users_routes.delete_user(ana.id, as_user(admin))
    assert stored_ids(auth_env, "users", "id") == [admin.id]
    assert stored_ids(auth_env, "profiles", "user_id") == [admin.id]

    error = failure(ana.id, admin)
    assert (error.status_code, error.detail) == (404, USER_NOT_FOUND)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.fixture
def carlos(make_user):
    return make_user("carlos@trackflow.test")


@pytest.mark.parametrize("actor", ["manager", "carlos"])
def test_manager_or_regular_user_cannot_delete_another_user(request, ana, actor):
    assert failure(ana.id, request.getfixturevalue(actor)).status_code == 403
    assert users_service.get_user(ana.id) is not None


def test_regular_user_gets_403_not_404_for_a_missing_id(ana):
    assert failure(MISSING_ID, ana).status_code == 403
