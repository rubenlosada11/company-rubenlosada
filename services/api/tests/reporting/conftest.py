"""Fixtures de los tests del pipeline semanal. Datos y utilidades en `tests/reporting/helpers.py`.

El pipeline es un flow de Prefect 3 (`data/pipelines/pipeline.py`): los tests lo ejecutan contra el servidor de pruebas
de Prefect (`prefect_test_harness`, una base temporal para toda la sesión, nunca `~/.prefect`), con los resultados
cacheados en una carpeta temporal y los snapshots de evaluación en la carpeta temporal de cada test.
"""

import os
import shutil
import tempfile
import uuid

import pytest

# Antes de que nada importe Prefect (lo importa `data.pipelines.pipeline`): caché de la sesión fuera del repo y sin
# analítica de uso.
_RESULTS_DIR = tempfile.mkdtemp(prefix="trackflow-prefect-results-")
os.environ["PREFECT_RESULTS_LOCAL_STORAGE_PATH"] = _RESULTS_DIR
os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"


@pytest.fixture(scope="session", autouse=True)
def prefect_server():
    """Servidor de Prefect temporal para toda la sesión (arrancarlo cuesta unos segundos)."""
    from prefect.testing.utilities import prefect_test_harness

    with prefect_test_harness():
        yield
    shutil.rmtree(_RESULTS_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def development_environment(monkeypatch):
    """El pipeline lee el entorno de `TELEMETRY_ENVIRONMENT`: los tests fijan `development` (el valor por defecto)."""
    monkeypatch.delenv("TELEMETRY_ENVIRONMENT", raising=False)


@pytest.fixture(autouse=True)
def eval_dir(tmp_path, monkeypatch):
    """Snapshots de evaluación (`write-eval-snapshot`) en la carpeta temporal del test, nunca en `data/eval/`."""
    path = tmp_path / "eval"
    monkeypatch.setenv("PIPELINE_EVAL_DIR", str(path))
    return path


@pytest.fixture(autouse=True)
def isolated_transform_cache(monkeypatch):
    """Cada test con su propia «versión del código» de la transformación y, por tanto, su propia caché.

    La clave de caché incluye la huella de los datos: dos tests con la misma extracción (p. ej. vacía) compartirían el
    resultado cacheado aunque uno sustituya `transform_events` por una función que falla. Sustituir la función es
    cambiar el código, y en producción eso cambia `CODE_VERSION`: aquí se simula igual. `test_pipeline_prefect.py`
    prueba la caché entre ejecuciones dentro de un mismo test.
    """
    from data.pipelines import pipeline

    monkeypatch.setattr(pipeline, "CODE_VERSION", f"test-{uuid.uuid4().hex}")
