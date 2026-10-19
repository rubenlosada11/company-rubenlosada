"""`POST /auth/forgot-password` — pedir un enlace de recuperación (AUTH-088, TESTING.md §6, fila 6).

Se llama a la función del router con un `BackgroundTasks` propio y el emisor falso (`email_outbox`); las tareas en
segundo plano se ejecutan a mano con `run`, así se ve qué ocurre antes y después de responder. El servicio de
enlaces (`app/services/password_reset.py`), TinyDB y el reloj (`clock`) son reales o están controlados, no simulados.
"""

import json
import logging
import urllib.parse
from datetime import datetime, timedelta

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.auth_models import ForgotPasswordRequest
from app.routes.auth import FORGOT_PASSWORD_MESSAGE, forgot_password
from app.security import ConfigError, get_frontend_base_url, get_reset_token_expire_minutes, hash_reset_token
from app.services import users as users_service
from app.services.email import EmailError
from app.services.password_reset import ResetTokenStatus, reset_token_status

from .conftest import T0


def ask(email: str, sender) -> tuple[str, BackgroundTasks]:
    tasks = BackgroundTasks()
    response = forgot_password(ForgotPasswordRequest(email=email), tasks, sender)
    return response.message, tasks


def run(tasks: BackgroundTasks) -> None:
    for task in tasks.tasks:
        task.func(*task.args, **task.kwargs)


def link_in(message) -> str:
    return next(line.strip() for line in message.text.splitlines() if "/reset-password?token=" in line)


def token_in(message) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(link_in(message)).query)["token"][0]


def stored_links(auth_env) -> list[dict]:
    return list(json.loads(auth_env.read_text(encoding="utf-8")).get("password_reset_tokens", {}).values())


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_active_user_gets_a_single_use_link_by_email_after_the_response(clock, ana, email_outbox, auth_env):
    message, tasks = ask("ana@trackflow.test", email_outbox)

    assert message == FORGOT_PASSWORD_MESSAGE
    assert email_outbox.sent == []  # el envío ocurre después de responder (no delata nada por el tiempo)
    run(tasks)

    (email,) = email_outbox.sent
    assert email.to == ana.email
    assert link_in(email).startswith("http://localhost:3002/reset-password?token=")
    token = token_in(email)
    assert reset_token_status(token) is ResetTokenStatus.VALID

    (link,) = stored_links(auth_env)
    assert link["token_hash"] == hash_reset_token(token)
    assert token not in auth_env.read_text(encoding="utf-8")  # el token en claro solo viaja en el email
    assert datetime.fromisoformat(link["expires_at"]) == T0 + timedelta(minutes=30)
    assert email.idempotency_key == f"password-reset/{link['id']}"


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_cooldown_blocks_a_second_link_until_exactly_60_seconds(clock, ana, email_outbox):
    _, tasks = ask("ana@trackflow.test", email_outbox)
    run(tasks)
    first = token_in(email_outbox.sent[0])

    clock.advance(seconds=59)
    message, tasks = ask("ana@trackflow.test", email_outbox)
    run(tasks)
    assert message == FORGOT_PASSWORD_MESSAGE
    assert len(email_outbox.sent) == 1
    assert reset_token_status(first) is ResetTokenStatus.VALID

    clock.advance(seconds=1)  # 60 s exactos desde la primera petición
    _, tasks = ask("ana@trackflow.test", email_outbox)
    run(tasks)
    assert len(email_outbox.sent) == 2
    assert reset_token_status(first) is ResetTokenStatus.NOT_FOUND  # solo vale el último enlace pedido
    assert reset_token_status(token_in(email_outbox.sent[1])) is ResetTokenStatus.VALID


def test_email_is_normalized_before_looking_up_the_user(ana, email_outbox):
    _, tasks = ask("  ANA@TrackFlow.Test ", email_outbox)
    run(tasks)
    assert [email.to for email in email_outbox.sent] == [ana.email]


def test_link_points_to_the_configured_backoffice_url(ana, email_outbox, monkeypatch):
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://backoffice.trackflow.test/")
    _, tasks = ask("ana@trackflow.test", email_outbox)
    run(tasks)
    assert link_in(email_outbox.sent[0]).startswith("https://backoffice.trackflow.test/reset-password?token=")


@pytest.mark.parametrize("minutes", [15, 60], ids=["minimo", "maximo"])
def test_link_lifetime_accepts_the_limits_of_its_window(clock, ana, email_outbox, auth_env, monkeypatch, minutes):
    monkeypatch.setenv("RESET_TOKEN_EXPIRE_MINUTES", str(minutes))
    ask("ana@trackflow.test", email_outbox)
    (link,) = stored_links(auth_env)
    assert datetime.fromisoformat(link["expires_at"]) == T0 + timedelta(minutes=minutes)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["inexistente", "desactivado"])
def test_unknown_or_deactivated_email_gets_the_same_answer_and_nothing_else(ana, email_outbox, auth_env, who):
    if who == "desactivado":
        users_service.update_user(ana.id, {"is_active": False})
    email = "nadie@trackflow.test" if who == "inexistente" else "ana@trackflow.test"

    message, tasks = ask(email, email_outbox)

    assert message == FORGOT_PASSWORD_MESSAGE
    assert tasks.tasks == [] and email_outbox.sent == []
    assert stored_links(auth_env) == []


def test_provider_failure_keeps_the_generic_answer_and_logs_without_secrets(ana, email_outbox, caplog):
    email_outbox.error = EmailError(429, "rate_limit_exceeded")

    message, tasks = ask("ana@trackflow.test", email_outbox)
    with caplog.at_level(logging.WARNING, logger="trackflow.email"):
        run(tasks)  # no debe lanzar

    assert message == FORGOT_PASSWORD_MESSAGE
    assert "rate_limit_exceeded" in caplog.text and ana.id in caplog.text
    assert ana.email not in caplog.text and "token=" not in caplog.text


@pytest.mark.parametrize("email", ["no-es-un-email", "ana@trackflow", "", "a" * 250 + "@t.es"])
def test_malformed_email_is_rejected_before_looking_anything_up(email):
    with pytest.raises(ValidationError):
        ForgotPasswordRequest(email=email)


@pytest.mark.parametrize("minutes", ["14", "61", "media-hora"])
def test_link_lifetime_outside_its_window_is_a_config_error(monkeypatch, minutes):
    monkeypatch.setenv("RESET_TOKEN_EXPIRE_MINUTES", minutes)
    with pytest.raises(ConfigError):
        get_reset_token_expire_minutes()


@pytest.mark.parametrize(
    "url", ["backoffice.trackflow.test", "ftp://backoffice.trackflow.test", "https://backoffice.trackflow.test?a=1"]
)
def test_backoffice_url_that_cannot_go_in_an_email_is_a_config_error(monkeypatch, url):
    monkeypatch.setenv("FRONTEND_BASE_URL", url)
    with pytest.raises(ConfigError):
        get_frontend_base_url()
