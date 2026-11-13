"""Fixtures de los tests del pipeline semanal. Datos y utilidades en `tests/reporting/helpers.py`."""

import pytest


@pytest.fixture(autouse=True)
def development_environment(monkeypatch):
    """El pipeline lee el entorno de `TELEMETRY_ENVIRONMENT`: los tests fijan `development` (el valor por defecto)."""
    monkeypatch.delenv("TELEMETRY_ENVIRONMENT", raising=False)
