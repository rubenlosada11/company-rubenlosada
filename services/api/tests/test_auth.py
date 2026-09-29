"""Tests de autenticación y autorización: usuarios, perfiles, login, JWT, 401/403 y rutas protegidas.

Ejecutar desde services/api: uv run pytest
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from app.auth_models import Role, UserCreate, UserUpdate
from app.create_admin import create_or_promote_admin
from app.main import app
from app.security import ALGORITHM, ConfigError, check_auth_config, create_access_token, decode_access_token
from app.services import profiles as profiles_service
from app.services import users as users_service
from tests.conftest import PASSWORD, TEST_SECRET_KEY, bearer

NEW_USER = {"email": "Laura.Gomez@TrackFlow.test", "password": "contraseña-segura"}


def login(client, email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def token_for(user_id: str, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=5), **overrides}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, TEST_SECRET_KEY, algorithm=ALGORITHM)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ana(make_user):
    return make_user("ana@trackflow.test", name="Ana Whitfield", phone="+1 213 555 0100", address="Los Ángeles")


@pytest.fixture
def carlos(make_user):
    return make_user("carlos@trackflow.test", name="Carlos Vega")


@pytest.fixture
def admin(make_user):
    return make_user("admin@trackflow.test", Role.ADMIN)


@pytest.fixture
def manager(make_user):
    return make_user("manager@trackflow.test", Role.MANAGER)


# --- POST /users (registro público) ----------------------------------------------------------------------------


def test_register_creates_user_and_profile(anon_client, auth_env):
    payload = {**NEW_USER, "name": "Laura Gómez", "phone": "+34 976 000 000", "address": "Zaragoza"}
    response = anon_client.post("/users", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "laura.gomez@trackflow.test"  # normalizado
    assert body["role"] == "user" and body["is_active"] is True
    assert body["profile"]["user_id"] == body["id"]
    assert {k: body["profile"][k] for k in ("name", "phone", "address")} == {
        "name": "Laura Gómez", "phone": "+34 976 000 000", "address": "Zaragoza",
    }
    assert "hashed_password" not in body and "password" not in body

    stored = json.loads(auth_env.read_text(encoding="utf-8"))
    assert len(stored["users"]) == 1 and len(stored["profiles"]) == 1


def test_register_profile_fields_are_optional(anon_client):
    body = anon_client.post("/users", json=NEW_USER).json()
    assert body["profile"]["name"] is None and body["profile"]["phone"] is None


def test_password_is_stored_hashed_with_bcrypt(anon_client, auth_env):
    anon_client.post("/users", json=NEW_USER)
    raw = auth_env.read_text(encoding="utf-8")
    assert NEW_USER["password"] not in raw
    (user,) = json.loads(raw)["users"].values()
    assert user["hashed_password"].startswith("$2b$")
    assert "password" not in user


def test_user_document_has_no_profile_data_and_profile_has_no_credentials(anon_client, auth_env):
    anon_client.post("/users", json={**NEW_USER, "name": "Laura", "phone": "976000000", "address": "Zaragoza"})
    stored = json.loads(auth_env.read_text(encoding="utf-8"))
    (user,) = stored["users"].values()
    (profile,) = stored["profiles"].values()
    assert set(user) == {"id", "email", "hashed_password", "is_active", "role", "created_at"}
    assert set(profile) == {"id", "user_id", "name", "phone", "address"}
    assert profile["user_id"] == user["id"]


def test_register_duplicate_email_returns_409(anon_client):
    assert anon_client.post("/users", json=NEW_USER).status_code == 201
    response = anon_client.post("/users", json={**NEW_USER, "email": "  laura.gomez@trackflow.TEST "})
    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un usuario con ese email."}


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"role": "user"}, {"is_active": False}, {"id": "x"}])
def test_register_cannot_choose_role_or_state(anon_client, extra):
    assert anon_client.post("/users", json={**NEW_USER, **extra}).status_code == 422


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"email": "no-es-un-email"}, "email"),
        ({"password": "corta"}, "password"),
        ({"password": "ñ" * 37}, "password"),  # 74 bytes: más de lo que bcrypt admite
        ({"phone": "llámame"}, "phone"),
        ({"name": "x" * 101}, "name"),
    ],
)
def test_register_rejects_invalid_data(anon_client, override, field):
    response = anon_client.post("/users", json={**NEW_USER, **override})
    assert response.status_code == 422
    assert field in [err["loc"][-1] for err in response.json()["detail"]]


# --- Roles -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "manager", "user"])
def test_valid_roles_are_accepted(role):
    assert UserUpdate(role=role).role == Role(role)


@pytest.mark.parametrize("role", ["superadmin", "Admin", "", "root", 1])
def test_other_roles_are_rejected(role):
    with pytest.raises(ValidationError):
        UserUpdate(role=role)


def test_new_users_are_user_by_default():
    user, _ = users_service.create_user(UserCreate(**NEW_USER))
    assert user.role == Role.USER


def test_admin_can_set_each_valid_role(client, admin, ana):
    for role in ("manager", "admin", "user"):
        response = client.put(f"/users/{ana.id}", json={"role": role}, headers=bearer(admin))
        assert response.status_code == 200 and response.json()["role"] == role
    response = client.put(f"/users/{ana.id}", json={"role": "jefe"}, headers=bearer(admin))
    assert response.status_code == 422


# --- Login -----------------------------------------------------------------------------------------------------


def test_login_returns_signed_jwt_with_tinydb_id(anon_client, ana):
    response = login(anon_client, "ANA@trackflow.test ")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 30 * 60
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == ana.id
    assert claims["exp"] - claims["iat"] == 30 * 60
    with pytest.raises(Exception):
        jwt.decode(body["access_token"], "otra-clave-cualquiera-de-32-caracteres!!", algorithms=[ALGORITHM])


def test_login_expiration_is_configurable(anon_client, ana, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    body = login(anon_client, ana.email).json()
    claims = decode_access_token(body["access_token"])
    assert body["expires_in"] == 300 and claims["exp"] - claims["iat"] == 300


@pytest.mark.parametrize(
    ("email", "password"),
    [("ana@trackflow.test", "contraseña-mala"), ("nadie@trackflow.test", PASSWORD), ("no-email", PASSWORD)],
)
def test_bad_credentials_get_the_same_401(anon_client, ana, email, password):
    response = login(anon_client, email, password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Email o contraseña incorrectos."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_with_too_long_password_is_401_not_500(anon_client, ana):
    assert login(anon_client, ana.email, "x" * 100).status_code == 401


def test_inactive_user_cannot_login(anon_client, ana):
    users_service.update_user(ana.id, {"is_active": False})
    response = login(anon_client, ana.email)
    assert response.status_code == 403
    assert "desactivada" in response.json()["detail"]
    # Con contraseña incorrecta no se revela que la cuenta existe y está desactivada.
    assert login(anon_client, ana.email, "contraseña-mala").status_code == 401


def test_oauth2_form_login_for_swagger(anon_client, ana):
    response = anon_client.post("/auth/token", data={"username": "Ana@trackflow.test", "password": PASSWORD})
    assert response.status_code == 200
    assert decode_access_token(response.json()["access_token"])["sub"] == ana.id
    bad = anon_client.post("/auth/token", data={"username": ana.email, "password": "mala-mala"})
    assert bad.status_code == 401


def test_login_does_not_set_cookies(anon_client, ana):
    response = login(anon_client, ana.email)
    assert "set-cookie" not in response.headers


def test_openapi_declares_oauth2_bearer_scheme(anon_client):
    schema = anon_client.get("/openapi.json").json()
    scheme = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["type"] == "oauth2" and scheme["flows"]["password"]["tokenUrl"] == "auth/token"


# --- JWT / get_current_user -------------------------------------------------------------------------------------


def test_valid_token_gives_access(anon_client, ana):
    token = login(anon_client, ana.email).json()["access_token"]
    assert anon_client.get("/auth/me", headers=auth(token)).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer no-es-un-jwt"},
        {"Authorization": "Bearer a.b.c"},
        {"Authorization": "Basic YW5hOnNlY3JldG8="},
    ],
)
def test_missing_or_malformed_token_is_401(anon_client, headers):
    response = anon_client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_is_401(anon_client, ana):
    token = token_for(ana.id, exp=datetime.now(UTC) - timedelta(seconds=1))
    response = anon_client.get("/auth/me", headers=auth(token))
    assert response.status_code == 401
    assert response.json()["detail"] == "El token ha caducado. Inicia sesión de nuevo."


def test_token_signed_with_another_key_is_401(anon_client, ana):
    now = datetime.now(UTC)
    forged = jwt.encode({"sub": ana.id, "exp": now + timedelta(minutes=5)}, "x" * 40, algorithm=ALGORITHM)
    assert anon_client.get("/auth/me", headers=auth(forged)).status_code == 401


def test_unsigned_token_is_401(anon_client, ana):
    header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
    real = token_for(ana.id)
    unsigned = f"{header}.{real.split('.')[1]}."
    assert anon_client.get("/auth/me", headers=auth(unsigned)).status_code == 401


@pytest.mark.parametrize("missing", ["sub", "exp"])
def test_token_without_required_claim_is_401(anon_client, ana, missing):
    token = token_for(ana.id, **{missing: None})
    assert anon_client.get("/auth/me", headers=auth(token)).status_code == 401


def test_token_of_deleted_user_is_401(anon_client, ana):
    headers = bearer(ana)
    users_service.delete_user(ana.id)
    response = anon_client.get("/auth/me", headers=headers)
    assert response.status_code == 401 and response.json()["detail"] == "Token no válido."


def test_token_of_deactivated_user_is_401(anon_client, ana):
    headers = bearer(ana)
    users_service.update_user(ana.id, {"is_active": False})
    assert anon_client.get("/auth/me", headers=headers).status_code == 401


def test_token_for_unknown_id_is_401(anon_client):
    assert anon_client.get("/auth/me", headers=auth(token_for("00000000-no-existe"))).status_code == 401


# --- Configuración ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("secret", [None, "", "change-me", "demasiado-corta"])
def test_missing_or_weak_secret_key_is_rejected(monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("SECRET_KEY")
    else:
        monkeypatch.setenv("SECRET_KEY", secret)
    with pytest.raises(ConfigError):
        check_auth_config()


@pytest.mark.parametrize("minutes", ["0", "-5", "media hora"])
def test_invalid_expiration_is_rejected(monkeypatch, minutes):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", minutes)
    with pytest.raises(ConfigError):
        check_auth_config()


def test_api_does_not_start_without_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ConfigError), TestClient(app):
        pass


def test_create_access_token_uses_env_secret(ana):
    token, _ = create_access_token(ana.id)
    assert jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])["sub"] == ana.id


# --- GET /auth/me --------------------------------------------------------------------------------------------


def test_me_returns_email_role_and_profile(anon_client, ana):
    response = anon_client.get("/auth/me", headers=bearer(ana))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ana@trackflow.test" and body["role"] == "user"
    assert body["profile"]["name"] == "Ana Whitfield"
    assert body["profile"]["phone"] == "+1 213 555 0100"
    assert body["profile"]["address"] == "Los Ángeles"
    assert "hashed_password" not in json.dumps(body)


# --- /users (protegidas) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/users"), ("GET", "/users/x"), ("PUT", "/users/x"), ("DELETE", "/users/x")],
)
def test_user_routes_require_token(anon_client, method, path):
    response = anon_client.request(method, path, json={"email": "a@b.co"} if method == "PUT" else None)
    assert response.status_code == 401


def test_list_users_for_admin_and_manager_without_hashes(anon_client, admin, manager, ana):
    for staff in (admin, manager):
        response = anon_client.get("/users", headers=bearer(staff))
        assert response.status_code == 200
        assert {u["email"] for u in response.json()} == {admin.email, manager.email, ana.email}
        assert "hashed_password" not in response.text


def test_list_users_is_forbidden_for_regular_users(anon_client, ana):
    assert anon_client.get("/users", headers=bearer(ana)).status_code == 403


def test_get_own_user(anon_client, ana):
    response = anon_client.get(f"/users/{ana.id}", headers=bearer(ana))
    assert response.status_code == 200
    assert response.json()["email"] == ana.email and "hashed_password" not in response.json()


def test_get_other_user_is_403_for_regular_user(anon_client, ana, carlos):
    assert anon_client.get(f"/users/{carlos.id}", headers=bearer(ana)).status_code == 403
    # Mismo 403 con un id que no existe: no se puede averiguar qué ids hay.
    assert anon_client.get("/users/no-existe", headers=bearer(ana)).status_code == 403


def test_staff_can_get_other_users_and_gets_404_for_missing(anon_client, manager, ana):
    assert anon_client.get(f"/users/{ana.id}", headers=bearer(manager)).status_code == 200
    assert anon_client.get("/users/no-existe", headers=bearer(manager)).status_code == 404


def test_user_can_change_own_email_and_password(anon_client, ana):
    response = anon_client.put(
        f"/users/{ana.id}", json={"email": "ana.w@trackflow.test", "password": "otra-contraseña"}, headers=bearer(ana)
    )
    assert response.status_code == 200 and response.json()["email"] == "ana.w@trackflow.test"
    assert login(anon_client, "ana.w@trackflow.test", "otra-contraseña").status_code == 200
    assert login(anon_client, "ana.w@trackflow.test", PASSWORD).status_code == 401
    assert login(anon_client, "ana@trackflow.test", "otra-contraseña").status_code == 401


def test_user_cannot_modify_another_user(anon_client, ana, carlos):
    response = anon_client.put(f"/users/{carlos.id}", json={"password": "hackeada-123"}, headers=bearer(ana))
    assert response.status_code == 403
    assert login(anon_client, carlos.email).status_code == 200  # la contraseña de Carlos no cambió


@pytest.mark.parametrize("change", [{"role": "admin"}, {"is_active": False}])
def test_regular_user_cannot_change_own_role_or_state(anon_client, ana, change):
    assert anon_client.put(f"/users/{ana.id}", json=change, headers=bearer(ana)).status_code == 403
    assert users_service.get_user(ana.id).role == Role.USER


def test_manager_cannot_modify_other_users(anon_client, manager, ana):
    assert anon_client.put(f"/users/{ana.id}", json={"role": "manager"}, headers=bearer(manager)).status_code == 403


def test_admin_can_change_role_and_deactivate(anon_client, admin, ana):
    response = anon_client.put(f"/users/{ana.id}", json={"role": "manager"}, headers=bearer(admin))
    assert response.status_code == 200 and response.json()["role"] == "manager"
    response = anon_client.put(f"/users/{ana.id}", json={"is_active": False}, headers=bearer(admin))
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert login(anon_client, ana.email).status_code == 403


def test_admin_cannot_change_other_users_credentials(anon_client, admin, ana):
    response = anon_client.put(f"/users/{ana.id}", json={"password": "cambiada-por-admin"}, headers=bearer(admin))
    assert response.status_code == 403


def test_admin_update_of_missing_user_is_404(anon_client, admin):
    assert anon_client.put("/users/no-existe", json={"role": "user"}, headers=bearer(admin)).status_code == 404


def test_update_to_taken_email_is_409(anon_client, ana, carlos):
    response = anon_client.put(f"/users/{ana.id}", json={"email": carlos.email}, headers=bearer(ana))
    assert response.status_code == 409


@pytest.mark.parametrize("payload", [{}, {"role": None}, {"email": None}, {"name": "Ana"}, {"hashed_password": "x"}])
def test_update_rejects_empty_null_or_unknown_fields(anon_client, admin, payload):
    assert anon_client.put(f"/users/{admin.id}", json=payload, headers=bearer(admin)).status_code == 422


def test_user_can_delete_self_and_profile_is_removed(anon_client, ana, auth_env):
    assert anon_client.delete(f"/users/{ana.id}", headers=bearer(ana)).status_code == 204
    assert users_service.get_user(ana.id) is None
    assert profiles_service.get_profile_by_user_id(ana.id) is None
    stored = json.loads(auth_env.read_text(encoding="utf-8"))
    assert stored["users"] == {} and stored["profiles"] == {}


def test_user_cannot_delete_another_user(anon_client, ana, carlos):
    assert anon_client.delete(f"/users/{carlos.id}", headers=bearer(ana)).status_code == 403
    assert users_service.get_user(carlos.id) is not None


def test_admin_can_delete_another_user_and_profile(anon_client, admin, ana):
    assert anon_client.delete(f"/users/{ana.id}", headers=bearer(admin)).status_code == 204
    assert profiles_service.get_profile_by_user_id(ana.id) is None
    assert anon_client.delete(f"/users/{ana.id}", headers=bearer(admin)).status_code == 404


# --- /profiles/me ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_profile_routes_require_token(anon_client, method):
    assert anon_client.request(method, "/profiles/me", json={"name": "x"}).status_code == 401


def test_get_my_profile(anon_client, ana, carlos):
    response = anon_client.get("/profiles/me", headers=bearer(ana))
    assert response.status_code == 200
    assert response.json()["user_id"] == ana.id and response.json()["name"] == "Ana Whitfield"
    # Cada token ve solo su propio perfil.
    assert anon_client.get("/profiles/me", headers=bearer(carlos)).json()["name"] == "Carlos Vega"


def test_update_my_profile_only_changes_sent_fields(anon_client, ana, carlos):
    response = anon_client.put("/profiles/me", json={"phone": "+1 213 555 0199", "address": ""}, headers=bearer(ana))
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Ana Whitfield" and body["phone"] == "+1 213 555 0199" and body["address"] is None
    assert profiles_service.get_profile_by_user_id(carlos.id).name == "Carlos Vega"


@pytest.mark.parametrize("payload", [{}, {"user_id": "otro"}, {"email": "x@y.zz"}, {"role": "admin"}])
def test_profile_update_only_accepts_profile_fields(anon_client, ana, payload):
    assert anon_client.put("/profiles/me", json=payload, headers=bearer(ana)).status_code == 422


def test_profile_routes_do_not_accept_other_user_ids(anon_client, ana, carlos):
    """No existe `/profiles/{user_id}`: un usuario no puede leer el perfil de otro."""
    assert anon_client.get(f"/profiles/{carlos.id}", headers=bearer(ana)).status_code in (404, 405)
    assert anon_client.get("/profiles/me", params={"user_id": carlos.id}, headers=bearer(ana)).json()["user_id"] == ana.id


def test_missing_profile_is_recreated_empty(anon_client, ana):
    profiles_service.delete_profile(ana.id)
    body = anon_client.get("/profiles/me", headers=bearer(ana)).json()
    assert body["user_id"] == ana.id and body["name"] is None


# --- Rutas existentes protegidas -----------------------------------------------------------------------------

PROTECTED_EXISTING_ROUTES = [
    ("GET", "/suppliers"),
    ("POST", "/suppliers"),
    ("GET", "/suppliers/1"),
    ("PATCH", "/suppliers/1/rate"),
    ("PATCH", "/suppliers/1/status"),
    ("DELETE", "/suppliers/1"),
    ("POST", "/api/incidents/analyze"),
    ("GET", "/api/incidents/results/export"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_EXISTING_ROUTES)
def test_existing_routes_require_token(anon_client, method, path):
    response = anon_client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(("method", "path"), PROTECTED_EXISTING_ROUTES)
def test_existing_routes_reject_invalid_token(anon_client, method, path):
    assert anon_client.request(method, path, headers=auth("no-es-un-jwt")).status_code == 401


@pytest.mark.parametrize(("method", "path"), PROTECTED_EXISTING_ROUTES)
def test_existing_routes_reject_expired_token(anon_client, ana, method, path):
    token = token_for(ana.id, exp=datetime.now(UTC) - timedelta(minutes=1))
    assert anon_client.request(method, path, headers=auth(token)).status_code == 401


def test_existing_routes_work_with_a_token_from_login(anon_client, ana):
    """Flujo completo: login → Bearer → rutas de proveedores e incidencias."""
    headers = auth(login(anon_client, ana.email).json()["access_token"])
    supplier = {
        "name": "Transportes Ebro", "country": "Spain", "categories": ["carrier_last_mile"],
        "rate_per_shipment": 3.95, "currency": "EUR", "status": "active",
    }
    created = anon_client.post("/suppliers", json=supplier, headers=headers)
    assert created.status_code == 201
    assert anon_client.get("/suppliers", headers=headers).status_code == 200
    assert anon_client.patch("/suppliers/1/status", json={"status": "suspended"}, headers=headers).status_code == 200
    assert anon_client.get("/api/incidents/results/export", headers=headers).status_code == 404  # sin análisis


def test_health_stays_public(anon_client):
    assert anon_client.get("/health").json() == {"status": "ok"}


def test_register_and_login_stay_public(anon_client):
    assert anon_client.post("/users", json=NEW_USER).status_code == 201
    assert login(anon_client, NEW_USER["email"], NEW_USER["password"]).status_code == 200


def test_cors_allows_authorization_header_and_put(anon_client):
    response = anon_client.options(
        "/profiles/me",
        headers={
            "Origin": "http://localhost:3002",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


# --- create-admin ----------------------------------------------------------------------------------------------


def test_create_admin_creates_an_admin_that_can_login(anon_client):
    action, user_id = create_or_promote_admin(" Jefa@TrackFlow.test ", read_password=lambda _: PASSWORD)
    assert action == "creado"
    user = users_service.get_user(user_id)
    assert user.role == Role.ADMIN and user.email == "jefa@trackflow.test"
    assert login(anon_client, "jefa@trackflow.test").status_code == 200


def test_create_admin_promotes_existing_user_without_asking_password(ana):
    users_service.update_user(ana.id, {"is_active": False})

    def no_password(_):
        raise AssertionError("no debe pedir contraseña")

    assert create_or_promote_admin(ana.email, read_password=no_password) == ("promovido", ana.id)
    user = users_service.get_user(ana.id)
    assert user.role == Role.ADMIN and user.is_active


def test_create_admin_rejects_mismatched_passwords():
    answers = iter([PASSWORD, "otra-distinta"])
    with pytest.raises(ValueError, match="no coinciden"):
        create_or_promote_admin("jefa@trackflow.test", read_password=lambda _: next(answers))
    assert users_service.get_user_by_email("jefa@trackflow.test") is None
