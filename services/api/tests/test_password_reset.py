"""Recuperación y cambio de contraseña (AUTH-03).

- Persistencia de los enlaces de recuperación (`app/services/password_reset.py`): estados del token, un solo uso
  (también simultáneo), caducidad, invalidación de enlaces anteriores, límite de reenvío y limpieza.
- `POST /auth/forgot-password`: misma respuesta exista o no el email, envío del enlace (con un emisor falso).
- `POST /auth/reset-password`: un solo uso, tokens no válidos, reglas de contraseña y cierre de sesiones abiertas.
"""

import json
import logging
import threading
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.auth_models import User
from app.dependencies import issued_after_password_change
from app.security import (
    ALGORITHM,
    ConfigError,
    check_auth_config,
    get_reset_token_expire_minutes,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.services import password_reset as reset_service
from app.main import app
from app.services.email import EmailError, get_email_sender
from app.services.password_reset import InvalidResetToken, ResetTokenStatus
from app.services.users import get_user, update_user
from tests.conftest import PASSWORD, TEST_SECRET_KEY, bearer

NEW_PASSWORD = "nueva-contraseña-segura"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def ana(make_user):
    return make_user("ana.ruiz@trackflow.test")


@pytest.fixture(scope="module")
def new_hash() -> str:
    # bcrypt tarda ~0,25 s: un solo hash para todo el módulo.
    return hash_password(NEW_PASSWORD)


def stored_tokens(auth_env) -> list[dict]:
    data = json.loads(auth_env.read_text(encoding="utf-8"))
    return list(data.get(reset_service.RESET_TOKENS_TABLE, {}).values())


# --- Emisión -----------------------------------------------------------------------------------------------------


def test_issue_stores_only_the_hash(ana, auth_env):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    raw = auth_env.read_text(encoding="utf-8")
    assert issued.token not in raw
    (record,) = stored_tokens(auth_env)
    assert set(record) == {"id", "user_id", "token_hash", "created_at", "expires_at", "used_at"}
    assert record["token_hash"] == hash_reset_token(issued.token)
    assert record["user_id"] == ana.id and record["id"] == issued.id
    assert record["used_at"] is None


def test_token_is_long_random_and_url_safe(ana, make_user):
    first = reset_service.issue_reset_token(ana.id, now=T0)
    second = reset_service.issue_reset_token(make_user("otra@trackflow.test").id, now=T0)
    assert first.token != second.token
    assert len(first.token) >= 43  # 32 bytes en base64 URL-safe
    assert set(first.token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_hash_is_sha256_hex():
    assert hash_reset_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_default_lifetime_is_30_minutes(ana):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    assert issued.expires_at == T0 + timedelta(minutes=30)


def test_lifetime_is_configurable(ana, monkeypatch):
    monkeypatch.setenv("RESET_TOKEN_EXPIRE_MINUTES", "15")
    assert reset_service.issue_reset_token(ana.id, now=T0).expires_at == T0 + timedelta(minutes=15)


def test_new_request_invalidates_previous_link(ana):
    first = reset_service.issue_reset_token(ana.id, now=T0)
    second = reset_service.issue_reset_token(ana.id, now=T0 + timedelta(minutes=2))
    assert reset_service.reset_token_status(first.token, now=T0 + timedelta(minutes=2)) is ResetTokenStatus.NOT_FOUND
    assert reset_service.reset_token_status(second.token, now=T0 + timedelta(minutes=2)) is ResetTokenStatus.VALID


def test_cooldown_blocks_a_second_request_within_60_seconds(ana, auth_env):
    first = reset_service.issue_reset_token(ana.id, now=T0)
    assert reset_service.issue_reset_token(ana.id, now=T0 + timedelta(seconds=59)) is None
    # El primer enlace sigue valiendo y no se ha creado otro.
    assert reset_service.reset_token_status(first.token, now=T0 + timedelta(seconds=59)) is ResetTokenStatus.VALID
    assert len(stored_tokens(auth_env)) == 1
    assert reset_service.issue_reset_token(ana.id, now=T0 + timedelta(seconds=60)) is not None


def test_cooldown_is_per_user(ana, make_user):
    assert reset_service.issue_reset_token(ana.id, now=T0) is not None
    assert reset_service.issue_reset_token(make_user("otra@trackflow.test").id, now=T0) is not None


def test_stale_tokens_are_purged_when_issuing(ana, make_user, auth_env, new_hash):
    old = reset_service.issue_reset_token(ana.id, now=T0)
    used = reset_service.issue_reset_token(make_user("luis@trackflow.test").id, now=T0)
    reset_service.consume_reset_token(used.token, new_hash, now=T0 + timedelta(minutes=1))
    assert len(stored_tokens(auth_env)) == 2

    # 1 día después de caducar el primero y de usar el segundo: se borran al emitir uno nuevo de otro usuario.
    later = T0 + timedelta(days=1, minutes=31)
    reset_service.issue_reset_token(make_user("eva@trackflow.test").id, now=later)
    remaining = stored_tokens(auth_env)
    assert len(remaining) == 1
    assert reset_service.reset_token_status(old.token, now=later) is ResetTokenStatus.NOT_FOUND


def test_recent_expired_token_is_kept_to_report_expired(ana, make_user):
    old = reset_service.issue_reset_token(ana.id, now=T0)
    later = T0 + timedelta(hours=2)
    reset_service.issue_reset_token(make_user("eva@trackflow.test").id, now=later)
    assert reset_service.reset_token_status(old.token, now=later) is ResetTokenStatus.EXPIRED


# --- Estados -----------------------------------------------------------------------------------------------------


def test_status_valid_expired_used_and_not_found(ana, new_hash):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    status = reset_service.reset_token_status
    assert status(issued.token, now=T0 + timedelta(minutes=29, seconds=59)) is ResetTokenStatus.VALID
    assert status(issued.token, now=T0 + timedelta(minutes=30)) is ResetTokenStatus.EXPIRED
    assert status("no-existe", now=T0) is ResetTokenStatus.NOT_FOUND
    reset_service.consume_reset_token(issued.token, new_hash, now=T0 + timedelta(minutes=1))
    assert status(issued.token, now=T0 + timedelta(minutes=2)) is ResetTokenStatus.USED


# --- Uso del token -----------------------------------------------------------------------------------------------


def test_consume_changes_password_and_marks_token_used(ana, auth_env, new_hash):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    used_at = T0 + timedelta(minutes=5)
    user = reset_service.consume_reset_token(issued.token, new_hash, now=used_at)

    assert isinstance(user, User) and user.id == ana.id
    assert user.password_changed_at == used_at
    stored = get_user(ana.id)
    assert verify_password(NEW_PASSWORD, stored.hashed_password)
    assert not verify_password(PASSWORD, stored.hashed_password)
    assert stored.password_changed_at == used_at
    (record,) = stored_tokens(auth_env)
    assert record["used_at"] == "2026-10-01T12:05:00Z"


def test_token_cannot_be_used_twice(ana, new_hash):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    reset_service.consume_reset_token(issued.token, new_hash, now=T0 + timedelta(minutes=1))
    other_hash = hash_password("otra-contraseña-123")
    with pytest.raises(InvalidResetToken):
        reset_service.consume_reset_token(issued.token, other_hash, now=T0 + timedelta(minutes=2))
    assert verify_password(NEW_PASSWORD, get_user(ana.id).hashed_password)


@pytest.mark.parametrize("delay", [timedelta(minutes=30), timedelta(hours=3)])
def test_expired_token_is_rejected_without_changes(ana, new_hash, delay):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    with pytest.raises(InvalidResetToken):
        reset_service.consume_reset_token(issued.token, new_hash, now=T0 + delay)
    stored = get_user(ana.id)
    assert verify_password(PASSWORD, stored.hashed_password) and stored.password_changed_at is None


def test_unknown_and_tampered_tokens_are_rejected(ana, new_hash):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    tampered = issued.token[:-1] + ("A" if issued.token[-1] != "A" else "B")
    for token in ("", "no-existe", tampered, issued.token + "x", hash_reset_token(issued.token)):
        with pytest.raises(InvalidResetToken):
            reset_service.consume_reset_token(token, new_hash, now=T0 + timedelta(minutes=1))
    assert verify_password(PASSWORD, get_user(ana.id).hashed_password)


def test_token_of_deactivated_user_is_rejected(ana, new_hash):
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    update_user(ana.id, {"is_active": False})
    with pytest.raises(InvalidResetToken):
        reset_service.consume_reset_token(issued.token, new_hash, now=T0 + timedelta(minutes=1))
    assert verify_password(PASSWORD, get_user(ana.id).hashed_password)


def test_token_of_deleted_user_is_rejected(ana, new_hash):
    from app.services.users import delete_user

    issued = reset_service.issue_reset_token(ana.id, now=T0)
    delete_user(ana.id)
    with pytest.raises(InvalidResetToken):
        reset_service.consume_reset_token(issued.token, new_hash, now=T0 + timedelta(minutes=1))


def test_token_only_changes_its_own_user(ana, make_user, new_hash):
    luis = make_user("luis@trackflow.test")
    issued = reset_service.issue_reset_token(ana.id, now=T0)
    reset_service.consume_reset_token(issued.token, new_hash, now=T0 + timedelta(minutes=1))
    assert verify_password(PASSWORD, get_user(luis.id).hashed_password)
    assert get_user(luis.id).password_changed_at is None


def test_concurrent_requests_with_same_token_succeed_only_once(ana, new_hash):
    issued = reset_service.issue_reset_token(ana.id)
    results: list[str] = []
    start = threading.Barrier(8)

    def attempt():
        start.wait()
        try:
            reset_service.consume_reset_token(issued.token, new_hash)
            results.append("ok")
        except InvalidResetToken:
            results.append("invalid")

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["invalid"] * 7 + ["ok"]


def test_revoke_removes_pending_tokens_only_for_that_user(ana, make_user):
    luis = make_user("luis@trackflow.test")
    mine = reset_service.issue_reset_token(ana.id, now=T0)
    theirs = reset_service.issue_reset_token(luis.id, now=T0)
    assert reset_service.revoke_reset_tokens(ana.id) == 1
    assert reset_service.reset_token_status(mine.token, now=T0) is ResetTokenStatus.NOT_FOUND
    assert reset_service.reset_token_status(theirs.token, now=T0) is ResetTokenStatus.VALID


# --- Modelo User y configuración ---------------------------------------------------------------------------------


def test_new_users_have_no_password_changed_at(ana, auth_env):
    assert ana.password_changed_at is None
    (doc,) = json.loads(auth_env.read_text(encoding="utf-8"))["users"].values()
    assert "password_changed_at" not in doc


def test_user_documents_from_before_auth03_still_load():
    legacy = {
        "id": "u1", "email": "a@trackflow.test", "hashed_password": "$2b$x", "is_active": True, "role": "user",
        "created_at": "2026-09-29T10:00:00Z",
    }
    assert User.model_validate(legacy).password_changed_at is None


@pytest.mark.parametrize("value, expected", [("", 30), ("15", 15), ("45", 45), ("60", 60)])
def test_reset_expire_minutes_accepts_15_to_60(monkeypatch, value, expected):
    monkeypatch.setenv("RESET_TOKEN_EXPIRE_MINUTES", value)
    assert get_reset_token_expire_minutes() == expected


@pytest.mark.parametrize("value", ["14", "61", "0", "-5", "abc", "30.5"])
def test_reset_expire_minutes_out_of_range_stops_the_api(monkeypatch, value):
    monkeypatch.setenv("RESET_TOKEN_EXPIRE_MINUTES", value)
    with pytest.raises(ConfigError, match="RESET_TOKEN_EXPIRE_MINUTES"):
        check_auth_config()


# --- POST /auth/forgot-password ----------------------------------------------------------------------------------

FORGOT = "/auth/forgot-password"
GENERIC = {"message": "Si esa dirección está registrada, recibirás un enlace para restablecer tu contraseña."}


class FakeSender:
    """Emisor de pruebas: guarda los emails en lugar de enviarlos (o falla con `error`)."""

    def __init__(self):
        self.sent = []
        self.error: Exception | None = None

    def send(self, message):
        if self.error is not None:
            raise self.error
        self.sent.append(message)
        return f"fake-{len(self.sent)}"


@pytest.fixture
def outbox():
    sender = FakeSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture
def api():
    return TestClient(app)


def token_from(message) -> str:
    """Token del enlace del email (versión de texto plano)."""
    url = next(line for line in message.text.splitlines() if "/reset-password?token=" in line)
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["token"][0]


def test_forgot_password_existing_email_sends_a_link(api, outbox, ana):
    response = api.post(FORGOT, json={"email": ana.email})
    assert response.status_code == 200
    assert response.json() == GENERIC

    (message,) = outbox.sent
    assert message.to == ana.email
    assert message.subject == "Restablece tu contraseña de TrackFlow"
    assert "http://localhost:3002/reset-password?token=" in message.text
    assert message.idempotency_key.startswith("password-reset/")
    token = token_from(message)
    assert f'href="http://localhost:3002/reset-password?token={token}"' in message.html
    assert reset_service.reset_token_status(token) is ResetTokenStatus.VALID


def test_forgot_password_unknown_email_gets_the_same_response_and_no_email(api, outbox, ana, auth_env):
    known = api.post(FORGOT, json={"email": ana.email})
    unknown = api.post(FORGOT, json={"email": "nadie@trackflow.test"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json() == GENERIC
    assert unknown.content == known.content
    ignore = {"date"}
    assert {k: v for k, v in unknown.headers.items() if k not in ignore} == {
        k: v for k, v in known.headers.items() if k not in ignore
    }
    assert [m.to for m in outbox.sent] == [ana.email]
    assert len(stored_tokens(auth_env)) == 1


def test_forgot_password_normalizes_the_email(api, outbox, ana):
    assert api.post(FORGOT, json={"email": "  Ana.Ruiz@TrackFlow.TEST "}).status_code == 200
    assert [m.to for m in outbox.sent] == [ana.email]


@pytest.mark.parametrize(
    "body",
    [
        {"email": "sin-arroba"}, {"email": ""}, {"email": "a@b"}, {"email": 123}, {"email": None}, {}, {"correo": "x"},
        {"email": "a" * 250 + "@trackflow.test"},
    ],
)
def test_forgot_password_invalid_format_is_422_without_email(api, outbox, ana, body):
    assert api.post(FORGOT, json=body).status_code == 422
    assert outbox.sent == []


def test_forgot_password_repeated_requests_within_a_minute_send_one_email(api, outbox, ana):
    for _ in range(3):
        response = api.post(FORGOT, json={"email": ana.email})
        assert response.status_code == 200 and response.json() == GENERIC
    assert len(outbox.sent) == 1
    assert reset_service.reset_token_status(token_from(outbox.sent[0])) is ResetTokenStatus.VALID


def test_forgot_password_after_cooldown_sends_a_new_link_and_voids_the_old_one(api, outbox, ana, monkeypatch):
    monkeypatch.setattr(reset_service, "REQUEST_COOLDOWN", timedelta(0))
    api.post(FORGOT, json={"email": ana.email})
    api.post(FORGOT, json={"email": ana.email})
    first, second = (token_from(m) for m in outbox.sent)
    assert first != second
    assert reset_service.reset_token_status(first) is ResetTokenStatus.NOT_FOUND
    assert reset_service.reset_token_status(second) is ResetTokenStatus.VALID


def test_forgot_password_inactive_user_gets_generic_response_and_no_email(api, outbox, ana, auth_env):
    update_user(ana.id, {"is_active": False})
    response = api.post(FORGOT, json={"email": ana.email})
    assert response.status_code == 200 and response.json() == GENERIC
    assert outbox.sent == [] and stored_tokens(auth_env) == []


@pytest.mark.parametrize(
    "error", [EmailError(403, "validation_error"), EmailError(0, "connection_error"), RuntimeError("caído")]
)
def test_forgot_password_provider_error_keeps_the_generic_200(api, outbox, ana, caplog, error):
    outbox.error = error
    caplog.set_level(logging.INFO, logger="trackflow")
    response = api.post(FORGOT, json={"email": ana.email})
    assert response.status_code == 200 and response.json() == GENERIC
    assert "no enviado" in caplog.text and ana.id in caplog.text
    assert ana.email not in caplog.text


def test_forgot_password_without_resend_key_responds_200_and_warns(api, ana, caplog):
    caplog.set_level(logging.INFO, logger="trackflow")
    response = api.post(FORGOT, json={"email": ana.email})
    assert response.status_code == 200 and response.json() == GENERIC
    assert "RESEND_API_KEY" in caplog.text


def test_forgot_password_never_logs_the_token_or_the_link(api, outbox, ana, caplog):
    caplog.set_level(logging.DEBUG)
    api.post(FORGOT, json={"email": ana.email})
    token = token_from(outbox.sent[0])
    assert token not in caplog.text and "reset-password?token" not in caplog.text


def test_forgot_password_link_uses_frontend_base_url(api, outbox, ana, monkeypatch):
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://backoffice.trackflow.test")
    api.post(FORGOT, json={"email": ana.email})
    assert "https://backoffice.trackflow.test/reset-password?token=" in outbox.sent[0].text


def test_forgot_password_is_public_and_ignores_tokens(api, outbox, ana):
    assert api.post(FORGOT, json={"email": ana.email}, headers={"Authorization": "Bearer basura"}).status_code == 200
    assert api.post(FORGOT, json={"email": "otra@trackflow.test"}, headers=bearer(ana)).status_code == 200
    assert "security" not in api.get("/openapi.json").json()["paths"][FORGOT]["post"]


def test_forgot_password_does_not_change_the_password_or_end_sessions(api, outbox, ana):
    api.post(FORGOT, json={"email": ana.email})
    assert verify_password(PASSWORD, get_user(ana.id).hashed_password)
    assert api.get("/auth/me", headers=bearer(ana)).status_code == 200
    assert api.post("/auth/login", json={"email": ana.email, "password": PASSWORD}).status_code == 200


# --- POST /auth/reset-password -----------------------------------------------------------------------------------

RESET = "/auth/reset-password"
INVALID_LINK = {"detail": "El enlace para restablecer la contraseña no es válido o ha caducado. Solicita uno nuevo."}
RESET_DONE = {"message": "Contraseña actualizada. Ya puedes iniciar sesión con la nueva contraseña."}


def old_bearer(user, seconds_ago: int = 5) -> dict[str, str]:
    """Bearer de una sesión abierta antes de ahora (su `iat` es de hace `seconds_ago` segundos)."""
    now = datetime.now(UTC)
    claims = {"sub": user.id, "iat": now - timedelta(seconds=seconds_ago), "exp": now + timedelta(minutes=30)}
    return {"Authorization": f"Bearer {jwt.encode(claims, TEST_SECRET_KEY, algorithm=ALGORITHM)}"}


def login(api, email: str, password: str) -> int:
    return api.post("/auth/login", json={"email": email, "password": password}).status_code


def test_reset_with_valid_token_changes_the_password(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    response = api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert response.json() == RESET_DONE
    assert login(api, ana.email, NEW_PASSWORD) == 200
    assert login(api, ana.email, PASSWORD) == 401
    assert reset_service.reset_token_status(issued.token) is ResetTokenStatus.USED
    assert get_user(ana.id).password_changed_at is not None


def test_reset_token_cannot_be_reused(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    assert api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD}).status_code == 200
    second = api.post(RESET, json={"token": issued.token, "new_password": "otra-contraseña-123"})
    assert second.status_code == 400
    assert second.json() == INVALID_LINK
    assert login(api, ana.email, NEW_PASSWORD) == 200
    assert login(api, ana.email, "otra-contraseña-123") == 401


def test_reset_with_expired_token_is_400(api, ana):
    issued = reset_service.issue_reset_token(ana.id, now=datetime.now(UTC) - timedelta(minutes=31))
    response = api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json() == INVALID_LINK
    assert login(api, ana.email, PASSWORD) == 200


def test_reset_with_token_from_a_previous_request_is_400(api, ana, monkeypatch):
    monkeypatch.setattr(reset_service, "REQUEST_COOLDOWN", timedelta(0))
    old = reset_service.issue_reset_token(ana.id)
    reset_service.issue_reset_token(ana.id)
    response = api.post(RESET, json={"token": old.token, "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json() == INVALID_LINK


def tampered(token: str) -> str:
    return token[:-1] + ("A" if token[-1] != "A" else "B")


@pytest.mark.parametrize(
    "make_token",
    [
        lambda t: "no-existe",
        lambda t: "",
        lambda t: " ",
        tampered,
        lambda t: t + "x",
        lambda t: t.upper(),
        lambda t: hash_reset_token(t),  # quien leyera la base de datos solo tiene el hash: no sirve
        lambda t: "x" * 512,
    ],
)
def test_reset_with_unknown_or_tampered_token_is_400(api, ana, make_token):
    issued = reset_service.issue_reset_token(ana.id)
    response = api.post(RESET, json={"token": make_token(issued.token), "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json() == INVALID_LINK
    assert login(api, ana.email, PASSWORD) == 200
    # El token bueno sigue valiendo: los intentos fallidos no lo gastan.
    assert reset_service.reset_token_status(issued.token) is ResetTokenStatus.VALID


@pytest.mark.parametrize(
    "new_password",
    ["corta", "", "a" * 73, "ñ" * 37],  # menos de 8 caracteres o más de 72 bytes
)
def test_reset_with_invalid_password_is_422_and_keeps_the_token(api, ana, new_password):
    issued = reset_service.issue_reset_token(ana.id)
    response = api.post(RESET, json={"token": issued.token, "new_password": new_password})
    assert response.status_code == 422
    assert reset_service.reset_token_status(issued.token) is ResetTokenStatus.VALID
    assert login(api, ana.email, PASSWORD) == 200


@pytest.mark.parametrize(
    "body",
    [{}, {"token": "x"}, {"new_password": NEW_PASSWORD}, {"token": None, "new_password": NEW_PASSWORD},
     {"token": 123, "new_password": NEW_PASSWORD}, {"token": "x" * 513, "new_password": NEW_PASSWORD}],
)
def test_reset_with_malformed_body_is_422(api, body):
    assert api.post(RESET, json=body).status_code == 422


def test_reset_for_deactivated_user_is_400(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    update_user(ana.id, {"is_active": False})
    response = api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json() == INVALID_LINK


def test_reset_closes_existing_sessions(api, ana, make_user):
    luis = make_user("luis@trackflow.test")
    before_ana, before_luis = old_bearer(ana), old_bearer(luis)
    assert api.get("/auth/me", headers=before_ana).status_code == 200

    issued = reset_service.issue_reset_token(ana.id)
    api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD})

    revoked = api.get("/auth/me", headers=before_ana)
    assert revoked.status_code == 401
    assert revoked.json() == {"detail": "Token no válido."}
    assert revoked.headers["www-authenticate"] == "Bearer"
    # Las sesiones de otros usuarios no se tocan.
    assert api.get("/auth/me", headers=before_luis).status_code == 200
    # Una sesión nueva con la contraseña nueva funciona.
    token = api.post("/auth/login", json={"email": ana.email, "password": NEW_PASSWORD}).json()["access_token"]
    assert api.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_reset_also_closes_sessions_on_protected_routes(api, ana, db_path):
    before = old_bearer(ana)
    assert api.get("/suppliers", headers=before).status_code == 200
    issued = reset_service.issue_reset_token(ana.id)
    api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD})
    assert api.get("/suppliers", headers=before).status_code == 401


def test_full_flow_forgot_email_reset_login(api, outbox, ana):
    assert api.post(FORGOT, json={"email": ana.email}).status_code == 200
    token = token_from(outbox.sent[0])
    assert api.post(RESET, json={"token": token, "new_password": NEW_PASSWORD}).status_code == 200
    assert login(api, ana.email, NEW_PASSWORD) == 200
    assert api.post(RESET, json={"token": token, "new_password": NEW_PASSWORD}).status_code == 400


def test_concurrent_resets_with_the_same_token_succeed_once(ana):
    issued = reset_service.issue_reset_token(ana.id)
    statuses: list[int] = []
    start = threading.Barrier(4)

    def attempt(password: str):
        client = TestClient(app)
        start.wait()
        statuses.append(client.post(RESET, json={"token": issued.token, "new_password": password}).status_code)

    passwords = [f"contraseña-paralela-{i}" for i in range(4)]
    threads = [threading.Thread(target=attempt, args=(p,)) for p in passwords]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 400, 400, 400]
    stored = get_user(ana.id).hashed_password
    assert sum(verify_password(p, stored) for p in passwords) == 1


def test_reset_is_public_and_does_not_log_the_token(api, ana, caplog):
    caplog.set_level(logging.DEBUG)
    issued = reset_service.issue_reset_token(ana.id)
    response = api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD},
                        headers={"Authorization": "Bearer basura"})
    assert response.status_code == 200
    assert issued.token not in caplog.text and NEW_PASSWORD not in caplog.text
    assert "security" not in api.get("/openapi.json").json()["paths"][RESET]["post"]


def test_invalid_token_is_rejected_before_spending_cpu_on_bcrypt(api, ana, monkeypatch):
    from app.routes import auth as auth_routes

    def no_bcrypt(_):
        raise AssertionError("bcrypt no debe ejecutarse con un token no válido")

    monkeypatch.setattr(auth_routes, "hash_password", no_bcrypt)
    assert api.post(RESET, json={"token": "inventado", "new_password": NEW_PASSWORD}).status_code == 400


def test_reset_response_reveals_nothing_about_the_user(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    body = api.post(RESET, json={"token": issued.token, "new_password": NEW_PASSWORD}).text
    assert ana.email not in body and ana.id not in body and "hashed" not in body


# --- Revocación de sesiones (password_changed_at frente a iat) ----------------------------------------------------


def with_change(user: User, changed_at: datetime | None) -> User:
    return user.model_copy(update={"password_changed_at": changed_at})


def test_tokens_are_valid_while_the_password_never_changed(ana):
    assert issued_after_password_change(0, ana)


@pytest.mark.parametrize(
    "iat, expected",
    [
        (int(T0.timestamp()) - 1, False),  # emitido antes del cambio
        (int(T0.timestamp()), True),  # mismo segundo: margen de 1 s
        (int(T0.timestamp()) + 60, True),  # emitido después (login con la contraseña nueva)
        (None, False),
        ("1790000000", False),
        (True, False),
    ],
)
def test_tokens_issued_before_the_change_are_rejected(ana, iat, expected):
    assert issued_after_password_change(iat, with_change(ana, T0 + timedelta(milliseconds=500))) is expected


# --- POST /auth/change-password ----------------------------------------------------------------------------------

CHANGE = "/auth/change-password"
WRONG_CURRENT = {"detail": "La contraseña actual no es correcta."}


def change(api, headers, current=PASSWORD, new=NEW_PASSWORD):
    return api.post(CHANGE, json={"current_password": current, "new_password": new}, headers=headers)


def test_change_password_with_correct_current_password(api, ana):
    response = change(api, old_bearer(ana))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"} and body["token_type"] == "bearer"
    assert login(api, ana.email, NEW_PASSWORD) == 200
    assert login(api, ana.email, PASSWORD) == 401
    assert get_user(ana.id).password_changed_at is not None


def test_change_password_returns_a_token_that_keeps_the_session(api, ana):
    before = old_bearer(ana)
    new_token = change(api, before).json()["access_token"]
    assert api.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    # La sesión con la que se hizo el cambio y cualquier otra anterior quedan cerradas.
    assert api.get("/auth/me", headers=before).status_code == 401


def test_change_password_closes_other_sessions_only_of_that_user(api, ana, make_user):
    luis = make_user("luis@trackflow.test")
    other_device, luis_session = old_bearer(ana, 30), old_bearer(luis)
    change(api, old_bearer(ana))
    assert api.get("/auth/me", headers=other_device).status_code == 401
    assert api.get("/auth/me", headers=luis_session).status_code == 200


def test_change_password_wrong_current_password_is_400_without_changes(api, ana):
    session = old_bearer(ana)
    response = change(api, session, current="no-es-la-actual")
    assert response.status_code == 400 and response.json() == WRONG_CURRENT
    assert "www-authenticate" not in response.headers  # no es un 401: el frontend no debe cerrar la sesión
    assert login(api, ana.email, PASSWORD) == 200
    assert api.get("/auth/me", headers=session).status_code == 200
    assert get_user(ana.id).password_changed_at is None


@pytest.mark.parametrize("current", ["", "a" * 73, "contraseña-segur", "CONTRASEÑA-SEGURA"])
def test_change_password_other_wrong_current_values_are_400(api, ana, current):
    response = change(api, bearer(ana), current=current)
    assert response.status_code == 400 and response.json() == WRONG_CURRENT


@pytest.mark.parametrize("new", ["corta", "", "a" * 73, "ñ" * 37])
def test_change_password_invalid_new_password_is_422(api, ana, new):
    assert change(api, bearer(ana), new=new).status_code == 422
    assert login(api, ana.email, PASSWORD) == 200


def test_change_password_new_equal_to_current_is_422(api, ana):
    response = change(api, bearer(ana), new=PASSWORD)
    assert response.status_code == 422
    assert "distinta de la actual" in response.text


@pytest.mark.parametrize(
    "body",
    [
        {}, {"current_password": PASSWORD}, {"new_password": NEW_PASSWORD},
        {"current_password": None, "new_password": "x" * 9},
        {"current_password": "x" * 201, "new_password": NEW_PASSWORD},
    ],
)
def test_change_password_malformed_body_is_422(api, ana, body):
    assert api.post(CHANGE, json=body, headers=bearer(ana)).status_code == 422


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer basura"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}],
)
def test_change_password_requires_a_valid_session(api, ana, headers):
    response = api.post(CHANGE, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert login(api, ana.email, PASSWORD) == 200


def test_change_password_with_expired_or_revoked_session_is_401(api, ana):
    now = datetime.now(UTC)
    expired = jwt.encode({"sub": ana.id, "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1)},
                         TEST_SECRET_KEY, algorithm=ALGORITHM)
    assert change(api, {"Authorization": f"Bearer {expired}"}).status_code == 401
    # Tras un cambio, la sesión anterior ya no sirve para hacer otro.
    before = old_bearer(ana)
    assert change(api, before).status_code == 200
    assert change(api, before, current=NEW_PASSWORD, new="tercera-contraseña").status_code == 401


def test_change_password_of_deactivated_user_is_401(api, ana):
    session = bearer(ana)
    update_user(ana.id, {"is_active": False})
    assert change(api, session).status_code == 401


def test_change_password_only_affects_the_token_owner(api, ana, make_user):
    # No hay id en la petición: con el token de Ana solo cambia la contraseña de Ana.
    luis = make_user("luis@trackflow.test")
    assert change(api, bearer(ana)).status_code == 200
    assert login(api, luis.email, PASSWORD) == 200
    assert login(api, luis.email, NEW_PASSWORD) == 401
    extra = api.post(CHANGE, json={"current_password": PASSWORD, "new_password": "x" * 10, "user_id": luis.id},
                     headers=bearer(luis))
    assert extra.status_code == 200  # el campo extra se ignora: cambia la de Luis, que es quien tiene la sesión
    assert login(api, ana.email, NEW_PASSWORD) == 200


def test_change_password_voids_pending_reset_links(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    change(api, bearer(ana))
    assert reset_service.reset_token_status(issued.token) is ResetTokenStatus.NOT_FOUND
    assert api.post(RESET, json={"token": issued.token, "new_password": "otra-contraseña-9"}).status_code == 400


def test_change_password_is_protected_in_openapi_and_does_not_log_passwords(api, ana, caplog):
    caplog.set_level(logging.DEBUG)
    change(api, bearer(ana))
    assert PASSWORD not in caplog.text and NEW_PASSWORD not in caplog.text
    assert api.get("/openapi.json").json()["paths"][CHANGE]["post"]["security"] == [{"OAuth2PasswordBearer": []}]


def test_put_users_no_longer_changes_passwords(api, ana):
    response = api.put(f"/users/{ana.id}", json={"password": NEW_PASSWORD}, headers=bearer(ana))
    assert response.status_code == 422
    assert login(api, ana.email, PASSWORD) == 200


# --- PUT /users/{id}: cambiar el email exige la contraseña actual --------------------------------------------------


def put_email(api, user, email, **extra):
    return api.put(f"/users/{user.id}", json={"email": email, **extra}, headers=bearer(user))


def test_email_change_without_current_password_is_400(api, ana):
    response = put_email(api, ana, "otro@trackflow.test")
    assert response.status_code == 400
    assert response.json() == {"detail": "Para cambiar el email, indica tu contraseña actual (current_password)."}
    assert get_user(ana.id).email == ana.email


@pytest.mark.parametrize("current", ["mal", "", NEW_PASSWORD, "a" * 73])
def test_email_change_with_wrong_current_password_is_400(api, ana, current):
    response = put_email(api, ana, "otro@trackflow.test", current_password=current)
    assert response.status_code == 400 and response.json() == WRONG_CURRENT
    assert get_user(ana.id).email == ana.email


def test_email_change_with_current_password_works(api, ana):
    response = put_email(api, ana, "otro@trackflow.test", current_password=PASSWORD)
    assert response.status_code == 200 and response.json()["email"] == "otro@trackflow.test"
    assert "current_password" not in response.text
    assert login(api, "otro@trackflow.test", PASSWORD) == 200


def test_email_change_voids_pending_reset_links(api, ana):
    issued = reset_service.issue_reset_token(ana.id)
    put_email(api, ana, "otro@trackflow.test", current_password=PASSWORD)
    assert reset_service.reset_token_status(issued.token) is ResetTokenStatus.NOT_FOUND


@pytest.mark.parametrize(
    "body",
    [
        {"current_password": PASSWORD},
        {"email": "x@trackflow.test", "current_password": None},
        {"email": "x@trackflow.test", "current_password": "x" * 201},
    ],
)
def test_put_users_current_password_alone_or_malformed_is_422(api, ana, body):
    assert api.put(f"/users/{ana.id}", json=body, headers=bearer(ana)).status_code == 422


def test_admin_role_changes_do_not_need_a_password(api, make_user, ana):
    from app.auth_models import Role

    admin = make_user("admin@trackflow.test", Role.ADMIN)
    assert api.put(f"/users/{ana.id}", json={"role": "manager"}, headers=bearer(admin)).status_code == 200


def test_permissions_are_checked_before_the_password(api, ana, make_user):
    luis = make_user("luis@trackflow.test")
    response = api.put(f"/users/{luis.id}", json={"email": "robado@trackflow.test"}, headers=bearer(ana))
    assert response.status_code == 403


def test_stolen_session_cannot_take_over_the_account_via_email_and_reset(api, outbox, ana):
    """Cadena cerrada: token robado → email del atacante → pedir un enlace → fijar una contraseña."""
    stolen = bearer(ana)
    response = api.put(f"/users/{ana.id}", json={"email": "atacante@trackflow.test"}, headers=stolen)
    assert response.status_code == 400
    assert api.put(f"/users/{ana.id}", json={"password": "del-atacante-1"}, headers=stolen).status_code == 422
    api.post(FORGOT, json={"email": "atacante@trackflow.test"})
    assert outbox.sent == []  # el email sigue siendo el de Ana: el atacante no recibe ningún enlace
    assert get_user(ana.id).email == ana.email and login(api, ana.email, PASSWORD) == 200
