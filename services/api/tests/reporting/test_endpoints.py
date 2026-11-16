"""Endpoints `/reporting` (`app/routes/reporting.py`, BRIEFING §6 y PIPELINE_DESIGN.md §11).

Contrato JSON, valores por defecto, permisos y errores (401, 403, 404, 422, 503). Desde DEV-55 el POST encola el
pipeline en Celery (202) y su resultado se lee en GET /tasks/{task_id}.

Ejecutar desde services/api: uv run pytest tests/reporting/test_endpoints.py
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from kombu.exceptions import OperationalError as BrokerError

from app.auth_models import Role
from app.main import app
from app.reporting import runner, runs
from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import last_complete_week
from app.routes import reporting as reporting_routes
from app.tasks import dead_letters
from app.tasks import registry as task_registry
from app.tasks import reporting as task_module
from data.pipelines import pipeline as flow
from data.pipelines.pipeline import PipelineAlreadyRunning, PipelineRunFailed, run_weekly_performance
from tests.conftest import bearer
from tests.reporting.helpers import DISCREPANCY, INBOUND, NOW, OUTBOUND, STOCKOUT, W1, W2, at, event, insert

REPORT = "/reporting/weekly-warehouse-client-performance"
LATEST_RUN = "/reporting/pipeline-runs/latest"
RUNS = "/reporting/pipeline-runs"
ENTRY_KEYS = {
    "warehouse",
    "client_id",
    "inbound_units_count",
    "outbound_orders_count",
    "stockout_events_count",
    "discrepancy_events_count",
    "discrepancy_rate",
}
RUN_KEYS = {
    "id",
    "pipeline",
    "status",
    "trigger",
    "triggered_by",
    "request_id",
    "environment",
    "week_from",
    "week_to",
    "phase",
    "started_at",
    "finished_at",
    "duration_ms",
    "events_read",
    "events_rejected",
    "rows_upserted",
    "rows_deleted",
    "stats",
    "error",
    "outcome",
}


@pytest.fixture
def user_api(make_user):
    return TestClient(app, headers=bearer(make_user("operaciones@trackflow.test")))


@pytest.fixture
def manager(make_user):
    return make_user("ana@trackflow.test", Role.MANAGER)


@pytest.fixture
def manager_api(manager):
    return TestClient(app, headers=bearer(manager))


@pytest.fixture
def computed():
    """Eventos en W1 y W2 y el pipeline ejecutado con «ahora» = NOW."""
    insert(
        event(INBOUND, at(W1), quantity=500, order_id=1),
        event(INBOUND, at(W2), quantity=4200, order_id=2),
        *(event(OUTBOUND, at(W2), order_id=10 + n) for n in range(980)),
        *(event(STOCKOUT, at(W2)) for _ in range(3)),
        *(event(DISCREPANCY, at(W2)) for _ in range(2)),
        event(OUTBOUND, at(W2), warehouse="zaragoza", client_id="electro-brand", order_id=1),
    )
    return run_weekly_performance(now=NOW)


@pytest.fixture
def frozen_now(monkeypatch):
    """«Ahora» = NOW en la API (que resuelve la ventana al encolar) y en el pipeline (que la vuelve a validar)."""
    original = flow.resolve_window

    def frozen(week_start, weeks, now=None):
        return original(week_start, weeks, NOW)

    monkeypatch.setattr(flow, "resolve_window", frozen)
    monkeypatch.setattr(reporting_routes, "resolve_window", frozen)


# --- GET /reporting/weekly-warehouse-client-performance -----------------------------------------------------------


def test_report_requires_authentication(anon_client):
    assert anon_client.get(REPORT).status_code == 401


def test_report_defaults_to_the_latest_computed_week_with_the_briefing_shape(user_api, computed):
    response = user_api.get(REPORT)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"week_start", "computed_at", "run_id", "entries"}
    assert body["week_start"] == W2.isoformat() and body["run_id"] == str(computed["id"])
    assert body["computed_at"].endswith("Z") or body["computed_at"].endswith("+00:00")
    assert all(set(entry) == ENTRY_KEYS for entry in body["entries"])
    assert body["entries"] == [
        {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "inbound_units_count": 4200,
            "outbound_orders_count": 980,
            "stockout_events_count": 3,
            "discrepancy_events_count": 2,
            "discrepancy_rate": 0.002,
        },
        {
            "warehouse": "zaragoza",
            "client_id": "electro-brand",
            "inbound_units_count": 0,
            "outbound_orders_count": 1,
            "stockout_events_count": 0,
            "discrepancy_events_count": 0,
            "discrepancy_rate": 0.0,
        },
    ]


def test_report_of_a_given_week(user_api, computed):
    body = user_api.get(REPORT, params={"week_start": W1.isoformat()}).json()
    assert body["week_start"] == W1.isoformat()
    assert [(e["client_id"], e["inbound_units_count"]) for e in body["entries"]] == [("fashion-co", 500)]


def test_computed_week_without_activity_is_200_with_empty_entries(user_api, computed):
    quiet = W1 - timedelta(days=7)
    run = run_weekly_performance(week_start=quiet, weeks=1, now=NOW)
    response = user_api.get(REPORT, params={"week_start": quiet.isoformat()})
    assert response.status_code == 200
    assert response.json()["entries"] == [] and response.json()["run_id"] == str(run["id"])


def test_week_never_computed_is_404_not_an_empty_report(user_api, computed):
    response = user_api.get(REPORT, params={"week_start": (W1 - timedelta(days=14)).isoformat()})
    assert response.status_code == 404 and "ninguna ejecución" in response.json()["detail"]


def test_failed_runs_do_not_count_as_computed(user_api, monkeypatch, frozen_now):
    monkeypatch.setattr(flow, "prepare_events", lambda *a: 1 / 0)
    with pytest.raises(PipelineRunFailed):
        run_weekly_performance()
    assert user_api.get(REPORT).status_code == 404


def test_no_computed_week_yet_is_404(user_api):
    response = user_api.get(REPORT)
    assert response.status_code == 404 and "POST /reporting/pipeline-runs" in response.json()["detail"]


@pytest.mark.parametrize("week_start", ["2026-11-03", "2026-13-01", "no-es-fecha"])
def test_week_start_must_be_a_monday_date(user_api, week_start):
    response = user_api.get(REPORT, params={"week_start": week_start})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "week_start"]


def test_report_storage_failure_is_503(user_api, monkeypatch):
    def broken(*args):
        raise ReportingStorageError("OperationalError")

    monkeypatch.setattr(runs, "latest_covered_week", broken)
    response = user_api.get(REPORT)
    assert response.status_code == 503 and "OperationalError" not in response.text


# --- GET /reporting/pipeline-runs/latest ---------------------------------------------------------------------------


def test_latest_run_requires_authentication(anon_client):
    assert anon_client.get(LATEST_RUN).status_code == 401


def test_latest_run_before_any_run_is_404(user_api):
    assert user_api.get(LATEST_RUN).status_code == 404


def test_latest_run_metadata(user_api, computed):
    body = user_api.get(LATEST_RUN).json()
    assert set(body) == RUN_KEYS
    assert body["id"] == str(computed["id"])
    assert body["status"] == "succeeded" and body["outcome"] == "succeeded" and body["trigger"] == "cli"
    assert (body["week_from"], body["week_to"]) == (W1.isoformat(), W2.isoformat())
    assert body["rows_upserted"] == 3 and body["events_read"] == 988
    assert body["stats"]["events_read"][STOCKOUT] == 3


def test_latest_run_storage_failure_is_503(user_api, monkeypatch):
    monkeypatch.setattr(runs, "latest_run", lambda pipeline: (_ for _ in ()).throw(ReportingStorageError("x")))
    assert user_api.get(LATEST_RUN).status_code == 503


# --- POST /reporting/pipeline-runs (productor asíncrono, DEV-55) -----------------------------------------------------
# El POST encola y responde 202 con el `task_id`. En los tests Celery ejecuta la tarea en el mismo proceso al encolarla
# (tests/conftest.py), así que al consultar GET /tasks/{task_id} ya ha terminado: se comprueba el mismo resultado que
# devolvía el antiguo POST síncrono, ahora en `result`.


def enqueue(api: TestClient, payload=None):
    """POST → 202 con solo el `task_id` y `Location`; devuelve (respuesta del POST, estado de la tarea)."""
    response = api.post(RUNS) if payload is None else api.post(RUNS, json=payload)
    assert response.status_code == 202, response.text
    assert set(response.json()) == {"task_id"}
    task_id = response.json()["task_id"]
    assert response.headers["location"] == f"/tasks/{task_id}"
    task = api.get(f"/tasks/{task_id}")
    assert task.status_code == 200
    return response, task.json()


def dead_letter(task_id: str) -> dict:
    row = dead_letters.get(task_id)
    assert row is not None, "el fallo definitivo debe quedar en la DLQ"
    return row


def test_run_requires_authentication(anon_client):
    assert anon_client.post(RUNS).status_code == 401


def test_plain_users_cannot_run_the_pipeline(user_api, fake_task_redis):
    response = user_api.post(RUNS)
    assert response.status_code == 403
    assert runs.latest_run(flow.PIPELINE_NAME) is None
    assert fake_task_redis.data == {}  # no se ha encolado nada


@pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
def test_staff_runs_the_default_window(make_user, role, frozen_now):
    user = make_user(f"{role}@trackflow.test", role)
    insert(event(OUTBOUND, at(W2), order_id=1))
    response, task = enqueue(TestClient(app, headers=bearer(user)))
    assert (task["status"], task["task_name"], task["error"]) == ("success", "reporting.run_weekly_performance", None)
    body = task["result"]
    assert set(body) == RUN_KEYS
    assert body["status"] == "succeeded" and body["trigger"] == "api" and body["triggered_by"] == user.id
    # El X-Request-Id de la respuesta 202 queda en la ejecución: une la petición, la tarea, sus logs y la corrida.
    assert body["request_id"] == response.headers["x-request-id"] and body["phase"] == "loaded"
    assert (body["week_from"], body["week_to"]) == (W1.isoformat(), W2.isoformat())
    assert body["rows_upserted"] == 1


def test_run_with_parameters(manager_api, frozen_now):
    _, task = enqueue(manager_api, {"week_start": W1.isoformat(), "weeks": 3})
    assert (task["result"]["week_from"], task["result"]["week_to"]) == ("2026-10-12", W1.isoformat())


def test_the_window_is_fixed_when_enqueuing(manager_api, frozen_now, monkeypatch):
    """La API resuelve la ventana al encolar: la tarea recibe la semana final explícita, no «la última completa»."""
    sent = {}
    monkeypatch.setattr(task_module.run_weekly_performance, "apply_async", lambda **options: sent.update(options))
    assert manager_api.post(RUNS, json={"weeks": 4}).status_code == 202
    assert sent["kwargs"]["week_start"] == W2.isoformat() and sent["kwargs"]["weeks"] == 4
    assert sent["expires"] == 3600 and sent["task_id"]


def test_run_then_read_the_report(manager_api, frozen_now):
    insert(event(INBOUND, at(W2), quantity=7, order_id=1))
    enqueue(manager_api, {})
    assert manager_api.get(REPORT).json()["entries"][0]["inbound_units_count"] == 7


@pytest.mark.parametrize(
    ("payload", "loc"),
    [
        ({"week_start": "2026-11-03"}, ["body", "week_start"]),  # martes
        ({"week_start": last_complete_week(NOW).isoformat(), "weeks": 0}, ["body", "weeks"]),
        ({"weeks": 54}, ["body", "weeks"]),
        ({"week_start": (W2 + timedelta(days=7)).isoformat()}, ["body", "week_start"]),  # semana en curso
        ({"semanas": 2}, ["body", "semanas"]),  # clave desconocida
    ],
)
def test_invalid_run_parameters_are_422_and_nothing_is_enqueued(
    manager_api, frozen_now, payload, loc, fake_task_redis
):
    response = manager_api.post(RUNS, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == loc
    assert runs.latest_run(flow.PIPELINE_NAME) is None
    assert fake_task_redis.data == {}


def test_run_in_progress_is_retried_with_backoff_and_ends_in_the_dlq(manager_api, monkeypatch):
    """Antes 409. Ahora otra ejecución en curso (p. ej. el cron) es un fallo transitorio: 1 intento + 3 reintentos."""
    calls = []

    def busy(**kwargs):
        calls.append(kwargs)
        raise PipelineAlreadyRunning("en curso")

    monkeypatch.setattr(flow, "run_weekly_performance", busy)
    _, task = enqueue(manager_api)
    assert len(calls) == 4
    assert task["status"] == "failure" and task["result"] is None
    assert task["error"]["type"] == "retries_exhausted" and "reintentos" in task["error"]["message"]
    row = dead_letter(task["task_id"])
    assert (row["reason"], row["attempts"], row["max_retries"]) == ("retries_exhausted", 4, 3)
    assert row["exception_type"] == "PipelineAlreadyRunning" and row["task_name"] == "reporting.run_weekly_performance"


def test_failed_run_is_a_permanent_failure_recorded_in_the_run_and_the_dlq(manager_api, frozen_now, monkeypatch):
    monkeypatch.setattr(flow, "prepare_events", lambda *a: 1 / 0)
    _, task = enqueue(manager_api)
    assert task["status"] == "failure" and task["error"]["type"] == "permanent_error"
    # El cliente no ve el error interno; el detalle está en la ejecución registrada y en la DLQ.
    assert "ZeroDivisionError" not in str(task)
    latest = manager_api.get(LATEST_RUN).json()
    assert latest["status"] == "failed" and latest["outcome"] == "failed" and latest["error"] == "ZeroDivisionError"
    row = dead_letter(task["task_id"])
    assert (row["reason"], row["attempts"], row["exception_type"]) == ("permanent_error", 1, "ZeroDivisionError")
    assert "PipelineRunFailed" in row["error_message"]
    assert row["task_kwargs"]["week_start"] == W2.isoformat()


def test_partial_run_succeeds_with_outcome_partial(manager_api, frozen_now, monkeypatch):
    """Falla una etapa opcional (observe): el reporte se carga y la ejecución se publica como parcial."""

    def broken(*args):
        raise ValueError("señal no disponible")

    monkeypatch.setattr(flow, "observe", broken)
    insert(event(OUTBOUND, at(W2), order_id=1))
    _, task = enqueue(manager_api)
    body = task["result"]
    assert task["status"] == "success"
    assert (body["status"], body["outcome"]) == ("succeeded", "partial")
    assert body["stats"]["degraded"] == ["observe"] and "observability_unavailable" in body["stats"]["warnings"]
    assert manager_api.get(LATEST_RUN).json()["outcome"] == "partial"
    assert manager_api.get(REPORT).json()["entries"][0]["outbound_orders_count"] == 1


def test_run_uses_the_pipeline_module_not_a_copy(manager_api, frozen_now):
    """El worker ejecuta el flow de data/pipelines: el id de la ejecución es el del flow run de Prefect."""
    assert runner.load_pipeline() is flow
    body = enqueue(manager_api)[1]["result"]
    assert body["stats"]["prefect"]["transform_cache"] == "miss"
    assert body["stats"]["prefect"]["code_version"] == flow.CODE_VERSION


def test_pipeline_unavailable_in_the_worker_is_a_permanent_failure(manager_api, monkeypatch):
    def unavailable():
        raise runner.PipelineUnavailable("No se encuentra data")

    monkeypatch.setattr(runner, "load_pipeline", unavailable)
    _, task = enqueue(manager_api)
    assert task["status"] == "failure" and task["error"]["type"] == "permanent_error"
    assert dead_letter(task["task_id"])["exception_type"] == "PipelineUnavailable"


@pytest.mark.parametrize(
    ("transient", "attempts", "reason"), [(False, 1, "permanent_error"), (True, 4, "retries_exhausted")]
)
def test_registry_unavailable_is_retried_only_if_transient(
    manager_api, frozen_now, monkeypatch, transient, attempts, reason
):
    calls = []

    def broken(**kwargs):
        calls.append(1)
        raise ReportingStorageError("OperationalError (SQLSTATE 08006)", transient=transient)

    # Sin los reintentos internos de Prefect (1 y 5 s): aquí se prueba el reintento de Celery de la tarea entera.
    monkeypatch.setattr(flow, "register_run", flow.register_run.with_options(retries=0))
    monkeypatch.setattr(runs, "start_run", broken)
    _, task = enqueue(manager_api)
    assert task["error"]["type"] == reason
    assert len(calls) == attempts
    row = dead_letter(task["task_id"])
    assert (row["reason"], row["attempts"], row["exception_type"]) == (reason, attempts, "ReportingStorageError")
    assert "SQLSTATE 08006" in row["error_message"]


def test_queue_unavailable_is_503_and_nothing_is_left_registered(manager_api, frozen_now, monkeypatch, fake_task_redis):
    def broker_down(**options):
        raise BrokerError("Error 111 connecting to redis:6379. Connection refused.")

    monkeypatch.setattr(task_module.run_weekly_performance, "apply_async", broker_down)
    response = manager_api.post(RUNS)
    assert response.status_code == 503 and "redis" not in response.text.lower()
    assert fake_task_redis.data == {}  # el registro del dueño se deshace
    assert runs.latest_run(flow.PIPELINE_NAME) is None


def test_registry_down_is_503_before_publishing(manager_api, frozen_now, monkeypatch):
    published = []

    def registry_down(*args):
        raise task_registry.TaskRegistryUnavailable("ConnectionError")

    monkeypatch.setattr(task_registry, "register", registry_down)
    monkeypatch.setattr(task_module.run_weekly_performance, "apply_async", lambda **o: published.append(o))
    assert manager_api.post(RUNS).status_code == 503
    assert published == []
