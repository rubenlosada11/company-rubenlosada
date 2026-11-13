"""Puente entre la API y el pipeline de `data/pipelines/` (Prefect 3).

El `POST /reporting/pipeline-runs` ejecuta **el mismo flow** que la línea de comandos: importa
`data.pipelines.pipeline` y llama a `run_weekly_performance`. La API no contiene lógica de extracción,
transformación ni carga.

La importación es perezosa (en la primera petición que la necesita) por dos motivos:

- Prefect es pesado de importar y arranca un servidor temporal la primera vez que se ejecuta un flow: los endpoints de
  lectura no lo necesitan y la API arranca igual de rápido.
- La imagen Docker de la API solo contiene `services/api/` (no `data/`): ahí el `POST` responde 503
  (`PipelineUnavailable`) en lugar de impedir que arranque la API entera.
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

# services/api/app/reporting/runner.py → raíz del monorepo.
REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_MODULE = "data.pipelines.pipeline"


class PipelineUnavailable(RuntimeError):
    """El pipeline (carpeta `data/` o Prefect) no está disponible en este despliegue."""


def load_pipeline() -> ModuleType:
    """Módulo `data.pipelines.pipeline`. `PipelineUnavailable` si no está en este despliegue."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))
    try:
        return importlib.import_module(PIPELINE_MODULE)
    except ModuleNotFoundError as error:
        if error.name and (error.name == "prefect" or PIPELINE_MODULE.startswith(error.name)):
            raise PipelineUnavailable(f"No se encuentra {error.name}") from None
        raise
