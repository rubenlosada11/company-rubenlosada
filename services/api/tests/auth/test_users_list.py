"""`GET /users` — listado de usuarios, solo para el staff (AUTH-088, TESTING.md §6, fila 9).

Se llama a la función del router con el usuario que entrega la dependencia real a partir de un token: el rol se lee de
la base en cada petición, no del token.
"""

import json

import pytest
from fastapi import HTTPException

from app.auth_models import Role
from app.dependencies import get_current_user
from app.routes import users as users_routes
from app.security import create_access_token
from app.services import users as users_service


def as_user(user):
    token, _ = create_access_token(user.id)
    return get_current_user(token)


# --- Camino feliz -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("staff_role", [Role.ADMIN, Role.MANAGER])
def test_staff_lists_every_user_in_creation_order_without_hashes(clock, make_user, staff_role):
    staff = make_user("staff@trackflow.test", staff_role)
    clock.advance(seconds=1)
    ana = make_user("ana@trackflow.test")
    clock.advance(seconds=1)
    carlos = make_user("carlos@trackflow.test")

    result = users_routes.list_users(as_user(staff))

    assert [user.id for user in result] == [staff.id, ana.id, carlos.id]
    assert "hashed_password" not in json.dumps([user.model_dump(mode="json") for user in result])


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_with_only_the_staff_member_the_list_has_one_user(admin):
    assert [user.id for user in users_routes.list_users(as_user(admin))] == [admin.id]


# --- Modos de fallo -----------------------------------------------------------------------------------------------


def test_regular_user_cannot_list_users(ana):
    with pytest.raises(HTTPException) as error:
        users_routes.list_users(as_user(ana))
    assert error.value.status_code == 403


def test_demoted_manager_loses_access_with_the_same_token(manager):
    token, _ = create_access_token(manager.id)
    users_service.update_user(manager.id, {"role": Role.USER})
    with pytest.raises(HTTPException) as error:
        users_routes.list_users(get_current_user(token))
    assert error.value.status_code == 403
