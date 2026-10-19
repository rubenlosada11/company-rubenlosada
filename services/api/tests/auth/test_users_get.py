"""`GET /users/{id}` — consulta de un usuario (AUTH-088, TESTING.md §6, fila 10).

Regla clave: los permisos se comprueban **antes** que la existencia, para que quien no es staff no pueda averiguar qué
ids existen (403 también para un id inexistente).
"""

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.routes import users as users_routes
from app.routes.users import USER_NOT_FOUND
from app.security import create_access_token

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def as_user(user):
    token, _ = create_access_token(user.id)
    return get_current_user(token)


def status_of(user_id: str, viewer) -> int:
    with pytest.raises(HTTPException) as error:
        users_routes.get_user(user_id, as_user(viewer))
    return error.value.status_code


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_user_reads_their_own_record_without_hash(ana):
    result = users_routes.get_user(ana.id, as_user(ana))
    assert (result.id, result.email) == (ana.id, ana.email)
    assert "hashed_password" not in result.model_dump()


@pytest.mark.parametrize("staff", ["admin", "manager"])
def test_staff_reads_other_users(request, ana, staff):
    viewer = request.getfixturevalue(staff)
    assert users_routes.get_user(ana.id, as_user(viewer)).id == ana.id


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_staff_gets_404_for_an_id_that_does_not_exist(manager):
    with pytest.raises(HTTPException) as error:
        users_routes.get_user(MISSING_ID, as_user(manager))
    assert (error.value.status_code, error.value.detail) == (404, USER_NOT_FOUND)


def test_regular_user_gets_403_not_404_for_an_id_that_does_not_exist(ana):
    assert status_of(MISSING_ID, ana) == 403


# --- Modo de fallo ------------------------------------------------------------------------------------------------


def test_regular_user_cannot_read_another_user(ana, make_user):
    carlos = make_user("carlos@trackflow.test")
    assert status_of(carlos.id, ana) == 403
