"""evaluation: snapshot JSON de cada ejecución en `data/eval/weekly_performance/` (PIPELINE_DESIGN.md §18.5).

Es la **task opcional** del flow: guarda, por ejecución, lo que se calculó y con qué calidad (ventana, eventos leídos y
rechazados por motivo, avisos, cambios por semana y las filas publicadas). Sirve para auditar un número del reporte
meses después sin volver a ejecutar nada, y para comparar ejecuciones entre sí.

No es crítica: si no se puede escribir (disco, permisos, ruta inexistente en un contenedor), el flow lo detecta con
`return_state=True`, marca la ejecución como **parcial** y el reporte ya cargado no se toca.

Directorio: `PIPELINE_EVAL_DIR` o, por defecto, `data/eval/weekly_performance/` (ignorado en git: son resultados de
ejecución, no código). Sin datos personales: almacén, cliente B2B, semana y contadores.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "eval" / "weekly_performance"


def eval_dir() -> Path:
    configured = os.environ.get("PIPELINE_EVAL_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_DIR


def write_snapshot(run_id: str, payload: dict[str, Any]) -> Path:
    """Escribe `<directorio>/<YYYYMMDDTHHMMSSZ>_<run_id>.json` y devuelve su ruta. `OSError` si no se puede."""
    directory = eval_dir()
    directory.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC)
    path = directory / f"{generated_at:%Y%m%dT%H%M%SZ}_{run_id}.json"
    document = {"run_id": run_id, "generated_at": generated_at.isoformat(), **payload}
    path.write_text(json.dumps(document, default=str, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
