"""`PUT /users/{id}` — cambio de email, rol o estado (AUTH-088, TESTING.md §6, fila 11).

Reglas: el email solo lo cambia su dueño y con `current_password` (un token robado no basta para desviar los enlaces
de recuperación); rol y estado solo los cambia un admin; los permisos se comprueban antes que la contraseña y que la
existencia. Se llama a la función del router con el usuario de la dependencia real y modelos `UserUpdate`.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth_models import Role, UserUpdate
from app.dependencies import get_current_user
from app.routes import users as users_routes
from app.routes.auth import authenticate
from app.routes.users import EMAIL_NEEDS_PASSWORD, EMAIL_TAKEN, USER_NOT_FOUND, WRONG_CURRENT_PASSWORD
from app.security import create_access_token
from app.services import users as users_service
from app.services.password_reset import ResetTokenStatus, issue_reset_token, reset_token_status
from conftest import PASSWORD

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def as_user(user):
    token, _ = create_access_token(user.id)
    return get_current_user(token)


def update(target_id: str, actor, **changes):
    return users_routes.update_user(target_id, UserUpdate(**changes), as_user(actor))


def failure(target_id: str, actor, **changes) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        update(target_id, actor, **changes)
    return error.value


@pytest.fixture
def carlos(make_user):
    return make_user("carlos@trackflow.test")


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_owner_changes_email_with_current_password_and_pending_links_die(ana):
    pending_link = issue_reset_token(ana.id).token

    result = update(ana.id, ana, email=" Ana.Nueva@TrackFlow.test ", current_password=PASSWORD)

    assert result.email == "ana.nueva@trackflow.test"
    assert authenticate("ana.nueva@trackflow.test", PASSWORD).id == ana.id
    # El enlace se envió al email anterior: ya no debe servir.
    assert reset_token_status(pending_link) is ResetTokenStatus.NOT_FOUND


def test_admin_changes_role_and_state_without_a_password(admin, ana):
    result = update(ana.id, admin, role="manager", is_active=False)
    assert (result.role, result.is_active) == (Role.MANAGER, False)


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_new_email_that_only_differs_in_case_is_not_a_conflict(ana):
    result = update(ana.id, ana, email="ANA@TRACKFLOW.TEST", current_password=PASSWORD)
    assert result.email == ana.email


def test_deactivation_by_an_admin_ends_the_users_session_at_once(admin, ana):
    token, _ = create_access_token(ana.id)
    update(ana.id, admin, is_active=False)
    with pytest.raises(HTTPException) as error:
        get_current_user(token)
    assert error.value.status_code == 401


# --- Modos de fallo: contraseña ------------------------------------------------------------------------------------


def test_email_change_without_current_password_is_400(ana):
    error = failure(ana.id, ana, email="otra@trackflow.test")
    assert (error.status_code, error.detail) == (400, EMAIL_NEEDS_PASSWORD)


def test_email_change_with_a_wrong_current_password_is_400_and_keeps_the_email(ana):
    error = failure(ana.id, ana, email="otra@trackflow.test", current_password="no-es-la-contraseña")
    assert (error.status_code, error.detail) == (400, WRONG_CURRENT_PASSWORD)
    assert users_service.get_user(ana.id).email == ana.email


# --- Modos de fallo: permisos --------------------------------------------------------------------------------------


@pytest.mark.parametrize("change", [{"role": "admin"}, {"is_active": False}], ids=["rol", "estado"])
def test_regular_user_cannot_change_own_role_or_state(ana, change):
    assert failure(ana.id, ana, **change).status_code == 403
    assert users_service.get_user(ana.id).role == Role.USER


def test_admin_cannot_change_the_email_of_another_user(admin, ana):
    assert failure(ana.id, admin, email="desvio@trackflow.test", current_password=PASSWORD).status_code == 403


@pytest.mark.parametrize("actor", ["manager", "carlos"])
def test_manager_or_regular_user_cannot_modify_another_user(request, ana, actor):
    assert failure(ana.id, request.getfixturevalue(actor), is_active=False).status_code == 403
    assert users_service.get_user(ana.id).is_active is True


def test_permissions_are_checked_before_the_password(ana, carlos):
    # Con un 400, carlos sabría que la petición era válida salvo por la contraseña.
    assert failure(ana.id, carlos, email="desvio@trackflow.test").status_code == 403


# --- Modos de fallo: datos ----------------------------------------------------------------------------------------


def test_email_of_another_user_is_409(ana, carlos):
    error = failure(ana.id, ana, email=carlos.email, current_password=PASSWORD)
    assert (error.status_code, error.detail) == (409, EMAIL_TAKEN)


def test_admin_updating_a_missing_user_gets_404(admin):
    error = failure(MISSING_ID, admin, is_active=False)
    assert (error.status_code, error.detail) == (404, USER_NOT_FOUND)


@pytest.mark.parametrize(
    "payload",
    [{}, {"current_password": PASSWORD}, {"password": "contraseña-nueva-2026"}, {"role": None}, {"role": "root"}],
    ids=["vacio", "solo-current-password", "password", "role-null", "role-inexistente"],
)
def test_update_payload_rules(payload):
    # La contraseña no se cambia aquí (AUTH-03): solo con change-password o con un enlace de recuperación.
    with pytest.raises(ValidationError):
        UserUpdate(**payload)
