"""Servicio de email (AUTH-03): configuración, petición a Resend, errores del proveedor, logs y plantilla.

Ningún test llama a Resend: `urllib.request.urlopen` se sustituye por un doble que guarda la petición.
"""

import io
import json
import logging
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.email_templates import PASSWORD_RESET_SUBJECT, password_reset_email
from app.main import app
from app.security import ConfigError, check_auth_config, get_frontend_base_url, password_reset_url
from app.services import email as email_service
from app.services.email import (
    DisabledSender,
    EmailError,
    EmailMessage,
    ResendSender,
    check_email_config,
    deliver,
    get_email_sender,
)

FAKE_KEY = "re_clave_de_pruebas_no_real_123"
SENDER = "TrackFlow <no-reply@trackflow.test>"
TOKEN = "tok3n-SECRETO_de-prueba"
RESET_URL = f"http://localhost:3002/reset-password?token={TOKEN}"
MESSAGE = EmailMessage(to="ana@trackflow.test", subject="Asunto", html="<p>Hola</p>", text="Hola", idempotency_key="k1")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured(monkeypatch):
    """Sustituye `urlopen`: guarda la petición y responde como Resend (`{"id": ...}`) o con el error indicado."""
    state: dict = {"response": b'{"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"}', "error": None}

    def fake_urlopen(request, timeout=None):
        state["request"] = request
        state["timeout"] = timeout
        if state["error"] is not None:
            raise state["error"]
        return FakeResponse(state["response"])

    monkeypatch.setattr(email_service.urllib.request, "urlopen", fake_urlopen)
    return state


def http_error(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(email_service.RESEND_API_URL, status, "error", {}, io.BytesIO(body))


# --- Configuración -----------------------------------------------------------------------------------------------


def test_without_api_key_the_sender_is_disabled():
    assert isinstance(get_email_sender(), DisabledSender)
    check_email_config()  # sin clave no se exige nada


def test_with_api_key_and_sender_uses_resend(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MAIL_FROM", SENDER)
    sender = get_email_sender()
    assert isinstance(sender, ResendSender)
    assert FAKE_KEY not in repr(sender)


@pytest.mark.parametrize(
    "mail_from",
    [
        None, "", "   ", "TrackFlow", "a@b.test\nBcc: x@y.test", "no-reply@", "@rubenlosada.com", "no-reply@localhost",
        "TrackFlow <no-reply@rubenlosada.com", "TrackFlow no-reply@rubenlosada.com", "<no-reply@rubenlosada.com>",
        # Errores de copia reales en el .env: la línea repetida y las comillas dentro del valor.
        "MAIL_FROM=TrackFlow <no-reply@rubenlosada.com>",
        'MAIL_FROM="TrackFlow <no-reply@rubenlosada.com>"',
        '"TrackFlow <no-reply@rubenlosada.com>"',
    ],
)
def test_api_key_without_valid_sender_stops_the_api(monkeypatch, mail_from):
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    if mail_from is not None:
        monkeypatch.setenv("MAIL_FROM", mail_from)
    with pytest.raises(ConfigError, match="MAIL_FROM"):
        check_email_config()


@pytest.mark.parametrize(
    "mail_from",
    ["no-reply@rubenlosada.com", "TrackFlow <no-reply@rubenlosada.com>", "TrackFlow Tech <onboarding@resend.dev>"],
)
def test_valid_senders(monkeypatch, mail_from):
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MAIL_FROM", mail_from)
    check_email_config()


def test_api_does_not_start_with_api_key_and_no_sender(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    with pytest.raises(ConfigError, match="MAIL_FROM"), TestClient(app):
        pass


def test_api_starts_without_email_config():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", "http://localhost:3002"),
        ("https://backoffice.trackflow.test/", "https://backoffice.trackflow.test"),
        ("http://127.0.0.1:3002", "http://127.0.0.1:3002"),
        ("https://ejemplo.test/backoffice", "https://ejemplo.test/backoffice"),
    ],
)
def test_frontend_base_url(monkeypatch, value, expected):
    monkeypatch.setenv("FRONTEND_BASE_URL", value)
    assert get_frontend_base_url() == expected


@pytest.mark.parametrize(
    "value", ["backoffice.trackflow.test", "ftp://x.test", "javascript:alert(1)", "https://", "https://x.test/?a=1"]
)
def test_invalid_frontend_base_url_stops_the_api(monkeypatch, value):
    monkeypatch.setenv("FRONTEND_BASE_URL", value)
    with pytest.raises(ConfigError, match="FRONTEND_BASE_URL"):
        check_auth_config()


def test_reset_url_points_to_the_backoffice_and_encodes_the_token(monkeypatch):
    assert password_reset_url("abc_-123") == "http://localhost:3002/reset-password?token=abc_-123"
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://backoffice.trackflow.test/")
    assert password_reset_url("a+b/c=") == "https://backoffice.trackflow.test/reset-password?token=a%2Bb%2Fc%3D"


# --- Petición a Resend -------------------------------------------------------------------------------------------


def test_resend_request_is_a_bearer_json_post(captured):
    provider_id = ResendSender(FAKE_KEY, SENDER).send(MESSAGE)
    assert provider_id == "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"

    request = captured["request"]
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_method() == "POST"
    headers = {name.lower(): value for name, value in request.header_items()}
    assert headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert headers["content-type"] == "application/json"
    assert headers["idempotency-key"] == "k1"
    assert headers["user-agent"] == "trackflow-api/0.1.0"
    assert json.loads(request.data) == {
        "from": SENDER, "to": ["ana@trackflow.test"], "subject": "Asunto", "html": "<p>Hola</p>", "text": "Hola",
    }
    assert captured["timeout"] == 10


def test_without_idempotency_key_the_header_is_not_sent(captured):
    ResendSender(FAKE_KEY, SENDER).send(EmailMessage(to="a@trackflow.test", subject="s", html="h", text="t"))
    assert "Idempotency-key" not in captured["request"].headers


def test_utf8_body(captured):
    message = EmailMessage(to="a@trackflow.test", subject="Contraseña", html="ñ", text="á")
    ResendSender(FAKE_KEY, SENDER).send(message)
    assert json.loads(captured["request"].data.decode("utf-8"))["subject"] == "Contraseña"


@pytest.mark.parametrize(
    "status, body, kind",
    [
        (403, b'{"statusCode": 403, "name": "validation_error", "message": "You can only send testing emails to x@y"}',
         "validation_error"),
        (401, b'{"name": "missing_api_key", "message": "Missing API key"}', "missing_api_key"),
        (429, b'{"name": "rate_limit_exceeded", "message": "Too many requests"}', "rate_limit_exceeded"),
        (500, b"<html>Internal Server Error</html>", "http_error"),
        (502, b"", "http_error"),
        (422, b'{"name": "x y; drop", "message": "raro"}', "http_error"),
    ],
)
def test_provider_errors_become_email_error_without_message(captured, status, body, kind):
    captured["error"] = http_error(status, body)
    with pytest.raises(EmailError) as excinfo:
        ResendSender(FAKE_KEY, SENDER).send(MESSAGE)
    assert (excinfo.value.status, excinfo.value.kind) == (status, kind)
    assert "x@y" not in str(excinfo.value) and "raro" not in str(excinfo.value)


@pytest.mark.parametrize("error", [urllib.error.URLError("sin red"), TimeoutError(), ConnectionResetError()])
def test_network_errors_become_email_error(captured, error):
    captured["error"] = error
    with pytest.raises(EmailError) as excinfo:
        ResendSender(FAKE_KEY, SENDER).send(MESSAGE)
    assert (excinfo.value.status, excinfo.value.kind) == (0, "connection_error")


def test_unreadable_success_response(captured):
    captured["response"] = b"no es json"
    with pytest.raises(EmailError, match="invalid_response"):
        ResendSender(FAKE_KEY, SENDER).send(MESSAGE)


# --- deliver y logs ----------------------------------------------------------------------------------------------


def reset_message() -> EmailMessage:
    return password_reset_email("ana@trackflow.test", RESET_URL, 30, idempotency_key="id-1")


def test_deliver_logs_success_without_sensitive_data(captured, caplog):
    caplog.set_level(logging.INFO, logger="trackflow.email")
    assert deliver(ResendSender(FAKE_KEY, SENDER), reset_message(), purpose="password_reset", user_id="u-1") is True
    assert "u-1" in caplog.text and "49a3999c" in caplog.text
    for secret in (TOKEN, FAKE_KEY, "ana@trackflow.test", PASSWORD_RESET_SUBJECT):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "error", [http_error(403, b'{"name": "validation_error", "message": "own email ana@trackflow.test"}'),
              urllib.error.URLError("sin red")],
)
def test_deliver_never_raises_and_logs_without_sensitive_data(captured, caplog, error):
    captured["error"] = error
    caplog.set_level(logging.INFO, logger="trackflow.email")
    assert deliver(ResendSender(FAKE_KEY, SENDER), reset_message(), purpose="password_reset", user_id="u-1") is False
    assert "no enviado" in caplog.text
    for secret in (TOKEN, FAKE_KEY, "ana@trackflow.test"):
        assert secret not in caplog.text


def test_deliver_survives_unexpected_errors(caplog):
    class Broken:
        def send(self, message):
            raise RuntimeError(f"fallo con {message.text}")

    caplog.set_level(logging.INFO, logger="trackflow.email")
    assert deliver(Broken(), reset_message(), purpose="password_reset", user_id="u-1") is False
    assert "RuntimeError" in caplog.text and TOKEN not in caplog.text


def test_disabled_sender_sends_nothing_and_warns(captured, caplog):
    caplog.set_level(logging.INFO, logger="trackflow.email")
    assert deliver(DisabledSender(), reset_message(), purpose="password_reset", user_id="u-1") is False
    assert "request" not in captured
    assert "RESEND_API_KEY" in caplog.text and TOKEN not in caplog.text


# --- Plantilla ---------------------------------------------------------------------------------------------------


def test_reset_email_content():
    message = reset_message()
    assert message.to == "ana@trackflow.test"
    assert message.subject == "Restablece tu contraseña de TrackFlow"
    assert message.idempotency_key == "id-1"
    for part in (message.html, message.text):
        assert RESET_URL in part
        assert "30 minutos" in part
        assert "solo se puede usar una vez" in part
        assert "Si no has pedido este cambio" in part
    assert 'lang="es"' in message.html
    assert 'name="viewport"' in message.html and "max-width:600px" in message.html
    assert "Restablecer contraseña</a>" in message.html


def test_reset_email_escapes_the_url_and_has_no_external_resources():
    message = password_reset_email("a@trackflow.test", 'https://x.test/reset-password?token=a"><script>&b=1', 15)
    assert "<script>" not in message.html
    assert 'href="https://x.test/reset-password?token=a&quot;&gt;&lt;script&gt;&amp;b=1"' in message.html
    assert "<img" not in message.html and "<link" not in message.html and "http://fonts" not in message.html
    assert "15 minutos" in message.html
