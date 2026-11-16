"""Extremo a extremo con servicios REALES (opcional): API en Docker → Redis → worker de Celery → PostgreSQL.

Sin dobles de prueba: peticiones HTTP a la API arrancada con `docker compose`, el worker ejecuta el pipeline real y la
DLQ se lee de la base. Se salta si faltan las variables. Requisitos (docs/async-tasks.md §9):

- `docker compose up -d redis backend worker` con `DATABASE_URL` apuntando a un PostgreSQL **local y desechable** con
  todas las migraciones aplicadas (los tests insertan y borran filas de `reporting.pipeline_runs` y renombran la tabla
  un momento para provocar un error permanente).
- `ASYNC_E2E_API_URL` (p. ej. `http://127.0.0.1:8000`), `ASYNC_E2E_DATABASE_URL` (la misma base vista desde el host;
  solo `localhost`/`127.0.0.1`), y tokens Bearer de dos managers distintos y de un admin: `ASYNC_E2E_MANAGER_TOKEN`,
  `ASYNC_E2E_OTHER_TOKEN`, `ASYNC_E2E_ADMIN_TOKEN`.

    uv run pytest tests/tasks/test_e2e_docker.py -v
"""

import os
import statistics
import time
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import create_engine, make_url, text

API = os.environ.get("ASYNC_E2E_API_URL", "").strip().rstrip("/")
DB = os.environ.get("ASYNC_E2E_DATABASE_URL", "").strip()
TOKENS = {name: os.environ.get(f"ASYNC_E2E_{name.upper()}_TOKEN", "").strip() for name in ("manager", "other", "admin")}

pytestmark = pytest.mark.skipif(
    not (API and DB and all(TOKENS.values())), reason="Sin ASYNC_E2E_* (stack Docker de pruebas opcional)"
)

PIPELINE = "weekly_warehouse_client_performance"
TERMINAL = {"success", "failure"}


@pytest.fixture(scope="module")
def engine():
    if make_url(DB).host not in ("localhost", "127.0.0.1"):
        pytest.fail("ASYNC_E2E_DATABASE_URL debe ser un PostgreSQL local y desechable")
    engine = create_engine(DB)
    yield engine
    engine.dispose()


def api(token: str = "manager") -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {TOKENS[token]}"}, timeout=10)


def wait_for(client: httpx.Client, task_id: str, timeout: float = 120) -> tuple[dict, list[str]]:
    """Consulta GET /tasks/{id} cada 100 ms hasta un estado final. Devuelve el último cuerpo y los estados vistos."""
    seen: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/tasks/{task_id}").json()
        if not seen or seen[-1] != body["status"]:
            seen.append(body["status"])
        if body["status"] in TERMINAL:
            return body, seen
        time.sleep(0.1)
    pytest.fail(f"La tarea {task_id} no terminó en {timeout} s (estados: {seen})")


def enqueue(client: httpx.Client) -> tuple[str, float]:
    started = time.perf_counter()
    response = client.post("/reporting/pipeline-runs")
    elapsed = time.perf_counter() - started
    assert response.status_code == 202, response.text
    assert response.headers["location"] == f"/tasks/{response.json()['task_id']}"
    return response.json()["task_id"], elapsed


def test_the_worker_completes_the_task_and_stores_the_run(engine):
    with api() as client:
        task_id, _ = enqueue(client)
        body, seen = wait_for(client, task_id)
    assert body["status"] == "success" and body["error"] is None, body
    assert seen[0] in ("pending", "started") and seen[-1] == "success"
    assert set(seen) <= {"pending", "started", "success"}
    run = body["result"]
    assert run["status"] == "succeeded" and run["trigger"] == "api"
    # La ejecución que devuelve la tarea es la que quedó registrada en la base por el worker.
    with engine.connect() as connection:
        stored = connection.execute(
            text("select status, trigger from reporting.pipeline_runs where id = :id"), {"id": run["id"]}
        ).one()
    assert tuple(stored) == ("succeeded", "api")


def test_the_202_answers_in_under_200_ms():
    """Con la API ya en marcha (la primera petición tras arrancar abre las conexiones con Redis: ver docs §8)."""
    with api() as client:
        client.get("/health")  # conexión HTTP ya abierta: se mide la API, no el handshake
        enqueue(client)  # calentamiento
        times = [enqueue(client)[1] for _ in range(5)]
        last = client.get("/tasks/" + client.post("/reporting/pipeline-runs").json()["task_id"]).json()
    assert statistics.median(times) < 0.2 and max(times) < 0.5, [round(t * 1000) for t in times]
    assert last["status"] in ("pending", "started")  # el 202 no ha esperado a la ejecución


def test_unknown_and_foreign_tasks_are_404():
    with api() as client:
        task_id, _ = enqueue(client)
        assert client.get(f"/tasks/{uuid.uuid4()}").status_code == 404
        assert client.get(f"/tasks/{task_id}").status_code == 200
    with api("other") as other:
        assert other.get(f"/tasks/{task_id}").status_code == 404


def test_a_persistent_transient_error_is_retried_with_backoff_and_ends_in_the_dlq(engine):
    """Una ejecución `running` ajena (p. ej. el cron) bloquea el pipeline: 1 intento + 3 reintentos (2, 4, 8 s)."""
    blocker = uuid.uuid4()
    with api() as client:
        wait_for(client, enqueue(client)[0])  # cola vacía: que no haya otra ejecución nuestra en marcha
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into reporting.pipeline_runs (id, pipeline, status, trigger, environment, week_from, "
                    "week_to, phase, started_at) values (:id, :pipeline, 'running', 'cli', 'development', "
                    "'2026-11-02', '2026-11-09', 'started', :now)"
                ),
                {"id": blocker, "pipeline": PIPELINE, "now": datetime.now(UTC)},
            )
        try:
            task_id, _ = enqueue(client)
            started = time.monotonic()
            body, seen = wait_for(client, task_id, timeout=90)
            elapsed = time.monotonic() - started
        finally:
            with engine.begin() as connection:
                connection.execute(text("delete from reporting.pipeline_runs where id = :id"), {"id": blocker})
    assert body["status"] == "failure" and body["error"]["type"] == "retries_exhausted"
    assert "retrying" in seen
    assert elapsed >= 2 + 4 + 8, f"Sin backoff real: {elapsed:.1f} s"
    with engine.connect() as connection:
        row = connection.execute(
            text("select reason, attempts, max_retries, exception_type from task_dead_letters where task_id = :id"),
            {"id": task_id},
        ).one()
    assert tuple(row) == ("retries_exhausted", 4, 3, "PipelineAlreadyRunning")


def test_a_permanent_error_fails_once_and_ends_in_the_dlq(engine):
    """Tabla del registro inexistente (migración sin aplicar, SQLSTATE 42P01): no se reintenta."""
    with api() as client:
        wait_for(client, enqueue(client)[0])
        with engine.begin() as connection:
            connection.execute(text("alter table reporting.pipeline_runs rename to pipeline_runs_e2e"))
        try:
            task_id, _ = enqueue(client)
            body, seen = wait_for(client, task_id, timeout=60)
        finally:
            with engine.begin() as connection:
                connection.execute(text("alter table reporting.pipeline_runs_e2e rename to pipeline_runs"))
    assert body["status"] == "failure" and body["error"]["type"] == "permanent_error"
    assert "retrying" not in seen and "42P01" not in str(body)
    with engine.connect() as connection:
        row = connection.execute(
            text("select reason, attempts, exception_type, error_message from task_dead_letters where task_id = :id"),
            {"id": task_id},
        ).one()
    assert (row.reason, row.attempts, row.exception_type) == ("permanent_error", 1, "ReportingStorageError")
    assert "42P01" in row.error_message


def test_admins_can_read_the_dead_letter_queue():
    with api("admin") as admin:
        body = admin.get("/tasks/dead-letters").json()
    assert body and {"retries_exhausted", "permanent_error"} <= {row["reason"] for row in body}
    with api() as manager:
        assert manager.get("/tasks/dead-letters").status_code == 403
