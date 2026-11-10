"""Configuración de la telemetría (variables de entorno, leídas en cada uso como el resto de la API).

- `TELEMETRY_ENDPOINT`: URL del colector definitivo al que la API **reenviará** los eventos cuando exista el
  almacenamiento (fase siguiente). En esta fase el receptor es un *stub* (`POST /telemetry/events`) que solo valida y
  registra: la variable se declara y se valida para fijar el patrón, pero no se envía nada a esa URL.
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


def log_telemetry_config() -> None:
    """Resumen al arrancar, sin secretos: qué falta y qué consecuencias tiene."""
    raw_endpoint = os.environ.get("TELEMETRY_ENDPOINT", "").strip()
    endpoint = get_telemetry_endpoint()
    if raw_endpoint and endpoint is None:
        logger.warning("TELEMETRY_ENDPOINT no es una URL http(s) válida: se ignora.")
    logger.info(
        "Telemetría en modo receptor temporal (POST /telemetry/events, sin almacenamiento). Entorno: %s. "
        "Colector definitivo (TELEMETRY_ENDPOINT): %s.",
        get_environment(),
        endpoint or "sin definir",
    )
    if get_pseudonym_key() is None:
        logger.warning(
            "Falta TELEMETRY_PSEUDONYM_KEY (o tiene menos de %d bytes): los eventos llegarán sin userId y los que lo "
            "exigen (órdenes de inventario, login correcto) se descartarán.",
            PSEUDONYM_KEY_MIN_BYTES,
        )
