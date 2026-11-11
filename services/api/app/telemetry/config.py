"""Configuración de la telemetría (variables de entorno, leídas en cada uso como el resto de la API).

- `DATABASE_URL`: base donde se guardan los eventos (`telemetry_events`, ver `storage`), la misma del inventario:
  Supabase/PostgreSQL con la migración aplicada, o SQLite local si no está definida.
- `TELEMETRY_ENDPOINT`: reservada para un colector externo. Desde la fase de almacenamiento los eventos se guardan
  directamente en `DATABASE_URL`, así que no se usa: solo se valida y se muestra al arrancar.
- `TELEMETRY_PSEUDONYM_KEY`: clave secreta (≥ 32 bytes) de los seudónimos HMAC `userId` y `account_ref` (§8.3). Solo
  en el `.env` de la API, nunca en el repositorio ni en el navegador. Sin ella, los eventos que exigen `userId` no se
  pueden emitir y se descartan con un aviso en el log.
- `TELEMETRY_ENVIRONMENT`: `development` (por defecto), `test` o `production`. Solo `production` alimentará los
  dashboards.

Ninguna de ellas impide arrancar la API: la telemetría nunca puede romper la operación (§15).
"""

import logging
import os
from typing import get_args
from urllib.parse import urlparse

from app.telemetry.models import Environment

logger = logging.getLogger("trackflow.telemetry")

PSEUDONYM_KEY_MIN_BYTES = 32
DEFAULT_ENVIRONMENT: Environment = "development"


def get_telemetry_endpoint() -> str | None:
    """URL `http(s)` del colector definitivo, o `None` si no está definida o no es válida."""
    value = os.environ.get("TELEMETRY_ENDPOINT", "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return value


def get_pseudonym_key() -> bytes | None:
    value = os.environ.get("TELEMETRY_PSEUDONYM_KEY", "").strip().encode("utf-8")
    return value if len(value) >= PSEUDONYM_KEY_MIN_BYTES else None


def get_environment() -> Environment:
    value = os.environ.get("TELEMETRY_ENVIRONMENT", "").strip()
    return value if value in get_args(Environment) else DEFAULT_ENVIRONMENT  # type: ignore[return-value]


def _storage_description() -> str:
    """Dónde se guardan los eventos, sin la cadena de conexión (lleva la contraseña)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "SQLite local db/inventory.db"
    return "SQLite de DATABASE_URL" if url.startswith("sqlite") else "PostgreSQL de DATABASE_URL"


def log_telemetry_config() -> None:
    """Resumen al arrancar, sin secretos: qué falta y qué consecuencias tiene."""
    raw_endpoint = os.environ.get("TELEMETRY_ENDPOINT", "").strip()
    endpoint = get_telemetry_endpoint()
    if raw_endpoint and endpoint is None:
        logger.warning("TELEMETRY_ENDPOINT no es una URL http(s) válida: se ignora.")
    logger.info(
        "Telemetría: POST /telemetry/events guarda los eventos en la tabla telemetry_events (%s). Entorno: %s. "
        "TELEMETRY_ENDPOINT (no se usa): %s.",
        _storage_description(),
        get_environment(),
        endpoint or "sin definir",
    )
    if get_pseudonym_key() is None:
        logger.warning(
            "Falta TELEMETRY_PSEUDONYM_KEY (o tiene menos de %d bytes): los eventos llegarán sin userId y los que lo "
            "exigen (órdenes de inventario, login correcto) se descartarán.",
            PSEUDONYM_KEY_MIN_BYTES,
        )
