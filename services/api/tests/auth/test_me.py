"""`GET /auth/me` — usuario autenticado y su perfil (AUTH-088, TESTING.md §6, fila 5).

La lógica de la ruta se prueba llamando a `me(current_user)` con el usuario tal y como lo entrega `get_current_user`.
El caso de fallo usa `TestClient` a propósito: lo que se comprueba es que **esta** ruta está protegida por la
dependencia (el cableado `Depends`), algo que no se ve llamando a la función.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.auth_models import Role
from app.dependencies import INVALID_TOKEN, NOT_AUTHENTICATED, get_current_user
from app.main import app
from app.routes.auth import me
from app.security import create_access_token
from app.services import profiles as profiles_service
from app.services import users as users_service


def current(user):
    """El usuario como lo ve la ruta: el que devuelve la dependencia a partir de un token real."""
    token, _ = create_access_token(user.id)
    return get_current_user(token)


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_me_returns_the_account_and_profile_without_credentials(make_user):
    laura = make_user("laura@trackflow.test", name="Laura Gómez", phone="+34 976 000 000")

    result = me(current(laura))

    assert (result.id, result.email, result.role, result.is_active) == (laura.id, laura.email, Role.USER, True)
    assert (result.profile.user_id, result.profile.name, result.profile.phone) == (
        laura.id, "Laura Gómez", "+34 976 000 000",
    )
    assert "hashed_password" not in json.dumps(result.model_dump(mode="json"))


def test_me_reflects_changes_made_after_the_token_was_issued(ana):
    token, _ = create_access_token(ana.id)
    users_service.update_user(ana.id, {"role": Role.MANAGER})
    # El rol sale de la base en cada petición, no del token: un ascenso o una degradación se aplica al momento.
    assert me(get_current_user(token)).role == Role.MANAGER


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_missing_profile_is_recreated_once_and_keeps_the_one_to_one_relation(ana, auth_env):
    profiles_service.delete_profile(ana.id)  # p. ej. datos creados a mano

    first = me(current(ana)).profile
    second = me(current(ana)).profile

    assert (first.name, first.phone, first.address) == (None, None, None)
    assert first.id == second.id
    profiles = json.loads(auth_env.read_text(encoding="utf-8"))["profiles"].values()
    assert [profile["user_id"] for profile in profiles] == [ana.id]


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.fixture
def api():
    return TestClient(app)


def test_me_without_token_is_401(api):
    response = api.get("/auth/me")
    assert (response.status_code, response.json()["detail"]) == (401, NOT_AUTHENTICATED)


def test_me_with_the_token_of_a_deactivated_user_is_401(api, ana):
    token, _ = create_access_token(ana.id)
    users_service.update_user(ana.id, {"is_active": False})
    response = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert (response.status_code, response.json()["detail"]) == (401, INVALID_TOKEN)
