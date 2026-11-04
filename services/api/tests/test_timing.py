"""`RequestTimingMiddleware` (`app/timing.py`): una línea de log por petición, sin datos sensibles.

Ejecutar desde services/api: uv run pytest tests/test_timing.py
"""

import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.timing import RequestTimingMiddleware

LINE = re.compile(r"^(GET|POST|PATCH|PUT|DELETE) (\S+) (\d{3}) \d+\.\d{2} ms( sql=\d+)?( error=\w+)?$")


def timing_lines(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "trackflow.api.timing"]


@pytest.fixture
def timing_log(caplog):
    caplog.set_level(logging.INFO, logger="trackflow.api.timing")
    return caplog


def test_logs_method_route_template_status_and_duration(client, timing_log):
    client.get("/suppliers/42")
    [line] = timing_lines(timing_log)
    match = LINE.match(line)
    assert match, line
    assert match.group(1, 2, 3) == ("GET", "/suppliers/{supplier_id}", "404")


def test_never_logs_query_strings_tokens_or_raw_ids(client, timing_log):
    client.get("/suppliers", params={"country": "Spain"})
    client.post("/auth/login", json={"email": "nadie@trackflow.test", "password": "contraseña-secreta"})
    text = "\n".join(timing_lines(timing_log))
    assert "country" not in text and "Spain" not in text
    assert "contraseña" not in text and "nadie@" not in text and "Bearer" not in text


def test_unknown_paths_are_not_logged_verbatim(client, timing_log):
    client.get("/no-existe/token-secreto")
    [line] = timing_lines(timing_log)
    assert "token-secreto" not in line
    assert line.startswith("GET <sin ruta> 404 ")


def test_counts_sql_queries_of_the_inventory(client, timing_log):
    client.get("/inventory/products")  # primera vez: también crea las tablas
    timing_log.clear()
    client.get("/inventory/products/1")
    [line] = timing_lines(timing_log)
    assert re.search(r" sql=\d+$", line), line


def test_tinydb_routes_do_not_report_sql(client, timing_log):
    client.get("/suppliers")
    [line] = timing_lines(timing_log)
    assert "sql=" not in line


def test_exceptions_are_timed_and_logged_with_their_type(timing_log):
    broken = FastAPI()
    broken.add_middleware(RequestTimingMiddleware)

    @broken.get("/boom")
    def boom() -> None:
        raise RuntimeError("detalle interno")

    with pytest.raises(RuntimeError):
        TestClient(broken).get("/boom")
    [record] = [record for record in timing_log.records if record.name == "trackflow.api.timing"]
    assert record.levelno == logging.ERROR
    assert LINE.match(record.getMessage()).group(2, 3, 5) == ("/boom", "500", " error=RuntimeError")
    assert "detalle interno" not in record.getMessage()


def test_api_errors_are_logged_with_the_final_500(client, timing_log, monkeypatch):
    from app.services import incidents as incidents_service

    monkeypatch.setattr(incidents_service, "summarize", lambda: 1 / 0)
    client.get("/api/incidents/summary")
    [line] = timing_lines(timing_log)
    assert line.startswith("GET /api/incidents/summary 500 ")


def test_middleware_is_installed_in_the_api():
    assert any(middleware.cls is RequestTimingMiddleware for middleware in app.user_middleware)
