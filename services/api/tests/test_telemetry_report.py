"""Reporte técnico `GET /telemetry/report` (`app/telemetry/report.py` y el router de telemetría).

Periodo por defecto y validación, estructura del JSON, integración con las funciones de `analysis` y caché de 60 s
(acierto dentro del TTL, recálculo al caducar, una entrada por periodo, peticiones simultáneas, errores no cacheados).

Ejecutar desde services/api: uv run pytest tests/test_telemetry_report.py
"""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.telemetry import analysis, report, storage
from app.telemetry.analysis import TelemetryAnalysisError
from app.telemetry.report import MAX_PERIOD, PeriodError, report_cache, resolve_period
from tests.conftest import bearer

METRIC_KEYS = {
    "events_per_day",
    "error_rate_by_type",
    "errors_per_day",
    "auth_failure_rate",
    "submission_failures_by_form",
}
NOW = datetime(2026, 11, 11, 20, 0, 30, 123456, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(report_cache, "clock", fake)
    return fake


@pytest.fixture
def api(make_user):
    return TestClient(app, headers=bearer(make_user("operaciones@trackflow.test")))


@pytest.fixture
def builds(monkeypatch) -> list[tuple[datetime, datetime]]:
    """Periodos con los que se ejecuta de verdad el pipeline (cada fallo de caché añade uno)."""
    calls: list[tuple[datetime, datetime]] = []
    original = report.build_report

    def spy(start, end):
        calls.append((start, end))
        return original(start, end)

    monkeypatch.setattr(report, "build_report", spy)
    return calls


def store(event_type: str, timestamp: datetime, tags: dict) -> None:
    row = {
        "id": uuid.uuid4(),
        "event_type": event_type,
        "timestamp": timestamp,
        "service": "backend",
        "tags": tags,
        "session_id": None,
        "user_id": None,
        "request_id": None,
        "schema_version": "1.0.0",
        "environment": "test",
    }
    with storage.telemetry_engine().begin() as connection:
        connection.execute(storage.telemetry_events.insert(), [row])


PERIOD = {"start_date": "2026-11-10T00:00:00Z", "end_date": "2026-11-12T00:00:00Z"}


# --- Periodo -------------------------------------------------------------------------------------------------------


def test_default_period_is_the_last_seven_days_up_to_the_next_minute():
    start, end = resolve_period(None, None, now=NOW)
    assert end == datetime(2026, 11, 11, 20, 1, tzinfo=UTC)
    assert start == end - timedelta(days=7)


def test_requests_in_the_same_minute_share_the_default_period():
    assert resolve_period(None, None, now=NOW) == resolve_period(None, None, now=NOW + timedelta(seconds=25))


def test_only_start_date_ends_now_and_only_end_date_starts_seven_days_before():
    start = datetime(2026, 11, 1, tzinfo=UTC)
    assert resolve_period(start, None, now=NOW) == (start, datetime(2026, 11, 11, 20, 1, tzinfo=UTC))
    end = datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert resolve_period(None, end, now=NOW) == (end - timedelta(days=7), end)


def test_dates_are_normalized_to_utc_and_naive_dates_are_utc():
    madrid = timezone(timedelta(hours=1))
    start, end = resolve_period(datetime(2026, 11, 10, 1, tzinfo=madrid), datetime(2026, 11, 12), now=NOW)
    assert start == datetime(2026, 11, 10, tzinfo=UTC) and start.tzinfo == UTC
    assert end == datetime(2026, 11, 12, tzinfo=UTC) and end.tzinfo == UTC


@pytest.mark.parametrize(
    ("start", "end", "field"),
    [
        (datetime(2026, 11, 12, tzinfo=UTC), datetime(2026, 11, 10, tzinfo=UTC), "start_date"),
        (datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 10, tzinfo=UTC), "start_date"),
        (datetime(2026, 11, 20, tzinfo=UTC), None, "start_date"),  # empieza después de ahora
        (datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 11, 10, tzinfo=UTC), "start_date"),  # más de 366 días
    ],
)
def test_invalid_periods_are_rejected(start, end, field):
    with pytest.raises(PeriodError) as error:
        resolve_period(start, end, now=NOW)
    assert error.value.field == field


def test_the_longest_period_is_accepted():
    end = datetime(2026, 11, 10, tzinfo=UTC)
    assert resolve_period(end - MAX_PERIOD, end, now=NOW) == (end - MAX_PERIOD, end)


# --- Endpoint ------------------------------------------------------------------------------------------------------


def test_report_without_parameters_covers_the_last_seven_days(api, builds):
    before = datetime.now(UTC)
    response = api.get("/telemetry/report")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"period", "metrics"} and set(body["metrics"]) == METRIC_KEYS
    start = datetime.fromisoformat(body["period"]["from"])
    end = datetime.fromisoformat(body["period"]["to"])
    assert body["period"]["to"].endswith("Z") and end.second == 0 and end.microsecond == 0
    assert before < end <= before + timedelta(minutes=1, seconds=5)
    assert end - start == timedelta(days=7)
    assert len(body["metrics"]["events_per_day"]) == 8  # 7 días que no empiezan a medianoche tocan 8 fechas


def test_report_with_both_dates_uses_the_pipeline_results(api):
    store("login_failed", datetime(2026, 11, 10, 9, tzinfo=UTC), {"failure_reason": "invalid_credentials"})
    store("login_succeeded", datetime(2026, 11, 10, 9, 1, tzinfo=UTC), {"user_role": "user"})
    store("form_submitted", datetime(2026, 11, 11, 9, tzinfo=UTC), {"form_id": "login", "outcome": "unauthorized"})
    store("login_failed", datetime(2026, 11, 12, 0, 0, tzinfo=UTC), {"failure_reason": "invalid_credentials"})  # fuera

    response = api.get("/telemetry/report", params=PERIOD)
    assert response.status_code == 200
    assert response.json() == {
        "period": {"from": "2026-11-10T00:00:00Z", "to": "2026-11-12T00:00:00Z"},
        "metrics": {
            "events_per_day": [
                {"date": "2026-11-10", "total_events": 2},
                {"date": "2026-11-11", "total_events": 1},
            ],
            "error_rate_by_type": [
                {
                    "error_category": "authentication",
                    "event_type": "login_failed",
                    "reason": "invalid_credentials",
                    "errors": 1,
                    "share_pct": 100.0,
                }
            ],
            "errors_per_day": [{"date": "2026-11-10", "errors": 1}, {"date": "2026-11-11", "errors": 0}],
            "auth_failure_rate": [
                {"date": "2026-11-10", "failed": 1, "succeeded": 1, "attempts": 2, "failure_rate_pct": 50.0}
            ],
            "submission_failures_by_form": [
                {"form_id": "login", "submissions": 1, "failed": 1, "failure_rate_pct": 100.0}
            ],
        },
    }


def test_report_with_only_one_date(api):
    response = api.get("/telemetry/report", params={"end_date": "2026-11-12T00:00:00Z"})
    assert response.status_code == 200
    assert response.json()["period"] == {"from": "2026-11-05T00:00:00Z", "to": "2026-11-12T00:00:00Z"}

    response = api.get("/telemetry/report", params={"start_date": "2026-11-10T00:00:00Z"})
    assert response.status_code == 200
    assert response.json()["period"]["from"] == "2026-11-10T00:00:00Z"


def test_report_accepts_offsets_and_dates_without_time(api):
    response = api.get(
        "/telemetry/report", params={"start_date": "2026-11-10T01:00:00+01:00", "end_date": "2026-11-12"}
    )
    assert response.status_code == 200
    assert response.json()["period"] == {"from": "2026-11-10T00:00:00Z", "to": "2026-11-12T00:00:00Z"}


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"start_date": "no-es-una-fecha"}, "start_date"),
        ({"end_date": "2026-02-30T00:00:00Z"}, "end_date"),
        ({"start_date": "2026-11-12T00:00:00Z", "end_date": "2026-11-10T00:00:00Z"}, "start_date"),
        ({"start_date": "2026-11-10T00:00:00Z", "end_date": "2026-11-10T00:00:00Z"}, "start_date"),
        ({"start_date": "2024-01-01T00:00:00Z", "end_date": "2026-11-10T00:00:00Z"}, "start_date"),
    ],
)
def test_invalid_periods_are_422_without_computing_anything(api, builds, params, field):
    response = api.get("/telemetry/report", params=params)
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["query", field] and "input" not in error
    assert builds == []


def test_report_requires_authentication_even_with_a_warm_cache(api, anon_client):
    assert api.get("/telemetry/report", params=PERIOD).status_code == 200
    assert anon_client.get("/telemetry/report", params=PERIOD).status_code == 401


def test_a_database_failure_is_a_503_and_is_not_cached(api, builds, monkeypatch):
    database_down = True
    original = analysis.auth_failure_rate

    def flaky(start, end):
        if database_down:
            raise TelemetryAnalysisError("OperationalError")
        return original(start, end)

    monkeypatch.setattr(analysis, "auth_failure_rate", flaky)
    response = api.get("/telemetry/report", params=PERIOD)
    assert response.status_code == 503
    assert "OperationalError" not in response.text
    assert report_cache.stats().entries == 0

    database_down = False  # la base vuelve: la siguiente petición calcula de nuevo, no hay nada guardado
    assert api.get("/telemetry/report", params=PERIOD).status_code == 200
    assert len(builds) == 2 and report_cache.stats().entries == 1


def test_report_is_documented_with_its_parameters_and_schema():
    operation = app.openapi()["paths"]["/telemetry/report"]["get"]
    assert {parameter["name"] for parameter in operation["parameters"]} == {"start_date", "end_date"}
    (content,) = operation["responses"]["200"]["content"].values()
    assert content["schema"]["$ref"].endswith("/TelemetryReport")
    assert {"401", "422", "503"} <= set(operation["responses"])


# --- Caché ---------------------------------------------------------------------------------------------------------


def test_first_request_computes_and_second_within_the_ttl_is_a_hit(api, builds, clock):
    first = api.get("/telemetry/report", params=PERIOD)
    clock.advance(59)
    store("login_failed", datetime(2026, 11, 10, 9, tzinfo=UTC), {"failure_reason": "invalid_credentials"})
    second = api.get("/telemetry/report", params=PERIOD)
    assert first.json() == second.json()  # el evento nuevo todavía no se ve
    assert len(builds) == 1
    assert report_cache.stats().hits == 1 and report_cache.stats().misses == 1


def test_the_report_is_recomputed_after_60_seconds(api, builds, clock):
    api.get("/telemetry/report", params=PERIOD)
    store("login_failed", datetime(2026, 11, 10, 9, tzinfo=UTC), {"failure_reason": "invalid_credentials"})
    clock.advance(60)
    body = api.get("/telemetry/report", params=PERIOD).json()
    assert len(builds) == 2
    assert body["metrics"]["errors_per_day"][0] == {"date": "2026-11-10", "errors": 1}


def test_each_period_has_its_own_cache_entry(api, builds, clock):
    store("login_failed", datetime(2026, 11, 10, 9, tzinfo=UTC), {"failure_reason": "invalid_credentials"})
    other = {"start_date": "2026-11-11T00:00:00Z", "end_date": "2026-11-12T00:00:00Z"}
    first = api.get("/telemetry/report", params=PERIOD).json()
    second = api.get("/telemetry/report", params=other).json()
    assert first["metrics"]["errors_per_day"] != second["metrics"]["errors_per_day"]
    assert second["period"]["from"] == "2026-11-11T00:00:00Z"
    assert len(builds) == 2 and report_cache.stats().entries == 2
    # Repetir cualquiera de los dos es un acierto con su propio resultado.
    assert api.get("/telemetry/report", params=other).json() == second
    assert api.get("/telemetry/report", params=PERIOD).json() == first
    assert len(builds) == 2


def test_the_same_instant_written_with_another_offset_shares_the_entry(api, builds, clock):
    api.get("/telemetry/report", params=PERIOD)
    api.get("/telemetry/report", params={"start_date": "2026-11-10T01:00:00+01:00", "end_date": "2026-11-12T00:00:00"})
    assert len(builds) == 1


def test_cache_key_includes_the_data_source(api, builds, tmp_path, monkeypatch):
    api.get("/telemetry/report", params=PERIOD)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'otra.db').as_posix()}")
    api.get("/telemetry/report", params=PERIOD)
    assert len(builds) == 2


def test_concurrent_requests_for_the_same_period_compute_once(monkeypatch):
    calls = []
    release = threading.Event()
    original = report.build_report

    def slow(start, end):
        calls.append((start, end))
        release.wait(5)
        return original(start, end)

    monkeypatch.setattr(report, "build_report", slow)
    start, end = datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC)
    results = []
    threads = [threading.Thread(target=lambda: results.append(report.get_report(start, end))) for _ in range(5)]
    for thread in threads:
        thread.start()
    time.sleep(0.2)  # todas las peticiones han llegado mientras la primera calcula
    release.set()
    for thread in threads:
        thread.join(5)
    assert len(calls) == 1 and len(results) == 5
    assert all(result == results[0] for result in results)


def test_different_periods_are_computed_in_parallel(monkeypatch):
    both_running = threading.Barrier(2, timeout=5)
    original = report.build_report

    def waits_for_the_other(start, end):
        both_running.wait()  # si un periodo bloqueara al otro, la barrera caducaría
        return original(start, end)

    monkeypatch.setattr(report, "build_report", waits_for_the_other)
    periods = [
        (datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 11, tzinfo=UTC)),
        (datetime(2026, 11, 11, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC)),
    ]
    errors = []

    def run(period):
        try:
            report.get_report(*period)
        except Exception as error:  # noqa: BLE001 — se comprueba abajo
            errors.append(error)

    threads = [threading.Thread(target=run, args=(period,)) for period in periods]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
