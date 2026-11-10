"""Identificadores de la telemetría: seudónimos (§8.3) y normalización de los campos de negocio (§8.4).

- `user_ref`: `"usr_" + hex(HMAC-SHA256(TELEMETRY_PSEUDONYM_KEY, "user:" + User.id))[:32]`. Nunca el id real.
- `account_ref`: lo mismo con el prefijo `"email:"` y el email normalizado (agrupa intentos de login fallidos).
- `client_slug`: `client_id` determinista a partir de `SKU.client_name` (el modelo no tiene id de cliente).
- `warehouse_id`: `LA` → `los_angeles`, `ZGZ` → `zaragoza`.
"""

import hashlib
import hmac
import re
import unicodedata

from app.telemetry.config import get_pseudonym_key

WAREHOUSES = {"LA": "los_angeles", "ZGZ": "zaragoza"}
CLIENT_ID_MAX_LENGTH = 64
UNKNOWN_CLIENT = "unknown-client"


def _pseudonym(prefix: str, domain: str, value: str) -> str | None:
    key = get_pseudonym_key()
    if key is None:
        return None
    digest = hmac.new(key, f"{domain}:{value}".encode(), hashlib.sha256).hexdigest()
    return f"{prefix}_{digest[:32]}"


def user_ref(user_id: str | None) -> str | None:
    """Seudónimo del usuario, o `None` si no hay usuario o falta la clave."""
    return _pseudonym("usr", "user", user_id) if user_id else None


def account_ref(email: str | None) -> str | None:
    """Seudónimo de un email de login (normalizado: sin espacios y en minúsculas, como `normalize_email`)."""
    normalized = (email or "").strip().lower()
    return _pseudonym("acc", "email", normalized) if normalized else None


def client_slug(client_name: str) -> str:
    """§8.4: NFKD sin diacríticos, minúsculas, todo lo que no sea `a-z0-9` → `-`, sin guiones extremos, ≤ 64."""
    ascii_name = unicodedata.normalize("NFKD", client_name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:CLIENT_ID_MAX_LENGTH].strip("-")
    return slug or UNKNOWN_CLIENT


def warehouse_id(code: str | None) -> str | None:
    """Almacén del contrato, o `None` si el valor interno no es uno de los dos almacenes."""
    return WAREHOUSES.get(code or "")
