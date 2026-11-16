"""`GET /tasks/{task_id}` y `GET /tasks/dead-letters` (`app/routes/tasks.py`, DEV-55).

Estados de Celery → contrato de la API, propiedad de la tarea (404 a otros usuarios), ids desconocidos, errores sin
detalles internos y Redis caído (503).
"""

import uuid

import pytest
import redis
from celery.result import AsyncResult
from fastapi.testclient import TestClient

from app.auth_models import Role
from app.main import app
from app.tasks import dead_letters, registry
from app.tasks.base import PermanentTaskError, RetriesExhausted, TaskTimedOut
from tests.conftest import bearer
from tests.tasks.helpers import flaky

STATUS_KEYS = {"task_id", "task_name", "status", "submitted_at", "result", "error"}


@pytest.fixture
def ana(make_user):
    return make_user("ana@trackflow.test", Role.MANAGER)


@pytest.fixture
def ana_api(ana):
    return TestClient(app, headers=bearer(ana))


def registered(owner, task_name: str = "tests.flaky") -> str:
    task_id = str(uuid.uuid4())
    registry.register(task_id, task_name, owner.id)
    return task_id


def with_state(monkeypatch, state: str, result=None) -> None:
    monkeypatch.setattr(AsyncResult, "state", property(lambda self: state))
    monkeypatch.setattr(AsyncResult, "result", property(lambda self: result))


def test_requires_authentication(anon_client):
    assert anon_client.get(f"/tasks/{uuid.uuid4()}").status_code == 401


def test_task_id_must_be_a_uuid(ana_api):
    assert ana_api.get("/tasks/no-es-un-uuid").status_code == 422


def test_unknown_task_is_404_not_pending(ana_api):
    """Celery diría PENDING para cualquier id: el registro de la API lo distingue."""
    response = ana_api.get(f"/tasks/{uuid.uuid4()}")
    assert response.status_code == 404 and "No existe" in response.json()["detail"]


def test_another_users_task_is_404(ana_api, make_user):
    other = make_user("carlos@trackflow.test", Role.ADMIN)
    task_id = registered(other)
    assert ana_api.get(f"/tasks/{task_id}").status_code == 404
    assert TestClient(app, headers=bearer(other)).get(f"/tasks/{task_id}").status_code == 200


@pytest.mark.parametrize(
    ("celery_state", "status"),
    [("PENDING", "pending"), ("RECEIVED", "pending"), ("STARTED", "started"), ("RETRY", "retrying")],
)
def test_in_progress_states(ana_api, ana, monkeypatch, celery_state, status):
    task_id = registered(ana)
    with_state(monkeypatch, celery_state)
    body = ana_api.get(f"/tasks/{task_id}").json()
    assert set(body) == STATUS_KEYS
    assert (body["task_id"], body["status"], body["result"], body["error"]) == (task_id, status, None, None)
    assert body["task_name"] == "tests.flaky" and body["submitted_at"]


def test_success_returns_the_result(ana_api, ana):
    task_id = str(uuid.uuid4())
    registry.register(task_id, flaky.name, ana.id)
    flaky.apply_async(kwargs={"failures": 1}, task_id=task_id)
    body = ana_api.get(f"/tasks/{task_id}").json()
    assert (body["status"], body["result"], body["error"]) == ("success", {"attempt": 2}, None)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (RetriesExhausted("ConnectionError tras 4 intentos"), "retries_exhausted"),
        (PermanentTaskError("ValueError en el intento 1"), "permanent_error"),
        (TaskTimedOut("SoftTimeLimitExceeded en el intento 1"), "time_limit"),
        (KeyError("postgresql://usuario:clave@host"), "unknown"),
    ],
)
def test_failure_returns_a_controlled_error(ana_api, ana, monkeypatch, error, kind):
    task_id = registered(ana)
    with_state(monkeypatch, "FAILURE", error)
    body = ana_api.get(f"/tasks/{task_id}").json()
    assert body["status"] == "failure" and body["result"] is None and body["error"]["type"] == kind
    # Ni el mensaje interno de la excepción ni credenciales: solo el mensaje fijo de su tipo.
    assert str(error) not in body["error"]["message"] and "clave" not in str(body)


def test_real_failure_end_to_end_in_process(ana_api, ana):
    task_id = str(uuid.uuid4())
    registry.register(task_id, flaky.name, ana.id)
    flaky.apply_async(kwargs={"failures": 10}, task_id=task_id)
    body = ana_api.get(f"/tasks/{task_id}").json()
    assert body["status"] == "failure" and body["error"]["type"] == "retries_exhausted"
    assert "DLQ" in body["error"]["message"] and "ConnectionError" not in str(body)


def test_revoked_is_a_failure_of_type_expired(ana_api, ana, monkeypatch):
    from celery.exceptions import TaskRevokedError

    task_id = registered(ana)
    with_state(monkeypatch, "REVOKED", TaskRevokedError("expired"))
    body = ana_api.get(f"/tasks/{task_id}").json()
    assert body["status"] == "failure" and body["error"]["type"] == "expired"


def test_registry_down_is_503(ana_api, monkeypatch):
    def down(task_id):
        raise registry.TaskRegistryUnavailable("ConnectionError")

    monkeypatch.setattr(registry, "lookup", down)
    response = ana_api.get(f"/tasks/{uuid.uuid4()}")
    assert response.status_code == 503 and "redis" not in response.text.lower()


def test_result_backend_down_is_503(ana_api, ana, monkeypatch):
    task_id = registered(ana)

    def down(self):
        raise redis.ConnectionError("Error 111 connecting to redis:6379")

    monkeypatch.setattr(AsyncResult, "state", property(down))
    assert ana_api.get(f"/tasks/{task_id}").status_code == 503


def test_registry_entries_expire_with_the_results(ana, fake_task_redis):
    task_id = registered(ana)
    assert fake_task_redis.ttl[registry.KEY_PREFIX + task_id] == 86400


# --- GET /tasks/dead-letters -----------------------------------------------------------------------------------------


def test_dead_letters_are_admin_only(ana_api, anon_client):
    assert anon_client.get("/tasks/dead-letters").status_code == 401
    assert ana_api.get("/tasks/dead-letters").status_code == 403


def test_dead_letters_list(make_user):
    admin = TestClient(app, headers=bearer(make_user("admin@trackflow.test", Role.ADMIN)))
    assert admin.get("/tasks/dead-letters").json() == []
    flaky.apply_async(kwargs={"failures": 10, "error": "permanent"})
    flaky.apply_async(kwargs={"failures": 10})
    body = admin.get("/tasks/dead-letters").json()
    assert [row["reason"] for row in body] == ["retries_exhausted", "permanent_error"]
    assert set(body[0]) == {
        "task_id",
        "task_name",
        "reason",
        "attempts",
        "max_retries",
        "exception_type",
        "error_message",
        "task_kwargs",
        "worker",
        "failed_at",
    }
    assert body[0]["failed_at"].endswith(("Z", "+00:00"))
    assert len(admin.get("/tasks/dead-letters", params={"limit": 1}).json()) == 1
    assert admin.get("/tasks/dead-letters", params={"limit": 0}).status_code == 422


def test_dead_letters_storage_error_is_503(make_user, monkeypatch):
    admin = TestClient(app, headers=bearer(make_user("admin@trackflow.test", Role.ADMIN)))

    def broken(limit):
        raise dead_letters.DeadLetterStorageError("OperationalError (SQLSTATE 08006)")

    monkeypatch.setattr(dead_letters, "latest", broken)
    response = admin.get("/tasks/dead-letters")
    assert response.status_code == 503 and "SQLSTATE" not in response.text
