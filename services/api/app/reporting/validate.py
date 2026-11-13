"""Subflow 2 · validate: reglas de calidad de los eventos de origen (PIPELINE_DESIGN.md §6.3).

Una fila que no cumple una regla se **rechaza**: no se corrige ni se imputa. Cada rechazo se cuenta por `event_type` y
motivo (el primero que falla, en el orden de `REASONS`) para el registro de la ejecución. Con Pandas, sin tocar la
base. Los valores de `tags` se comprueban por tipo exacto (un `"5"` de texto no es una cantidad, `True` tampoco).

| Motivo | Regla |
| --- | --- |
| `invalid_timestamp` | `timestamp` no interpretable como fecha |
| `invalid_warehouse` | `tags.warehouse` no es `los_angeles` ni `zaragoza` |
| `invalid_client_id` | `tags.client_id` no es un slug `^[a-z0-9]+(-[a-z0-9]+)*$` de 1–64 caracteres |
| `invalid_quantity` | `inbound_order_created` sin `tags.quantity` entero ≥ 1 (los demás eventos no la usan) |
| `duplicate_order` | Misma orden (`event_type` + `warehouse` + `order_id`) ya vista con otro `id`: cuenta la primera |
"""

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.reporting.extract import INBOUND, OUTBOUND, SOURCE_EVENT_TYPES

WAREHOUSES = ("los_angeles", "zaragoza")
CLIENT_ID_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"
CLIENT_ID_MAX_LENGTH = 64
ORDER_EVENT_TYPES = (INBOUND, OUTBOUND)

REASONS = ("invalid_timestamp", "invalid_warehouse", "invalid_client_id", "invalid_quantity", "duplicate_order")
VALID_COLUMNS = ["id", "event_type", "timestamp", "warehouse", "client_id", "quantity"]


@dataclass
class ValidationResult:
    """Eventos válidos (columnas `VALID_COLUMNS`, `timestamp` en UTC) y recuentos para el registro."""

    valid: pd.DataFrame
    events_read: dict[str, int] = field(default_factory=dict)
    rejected: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def events_rejected(self) -> int:
        return sum(sum(by_reason.values()) for by_reason in self.rejected.values())


_CLIENT_ID = re.compile(CLIENT_ID_PATTERN)


def _is_int(value: object, minimum: int) -> bool:
    # `bool` es subclase de `int` en Python: `True` no es una cantidad.
    return type(value) is int and value >= minimum


def _is_client_id(value: object) -> bool:
    return isinstance(value, str) and len(value) <= CLIENT_ID_MAX_LENGTH and _CLIENT_ID.fullmatch(value) is not None


def _tag(tags: pd.Series, key: str) -> pd.Series:
    """`tags[key]` de cada fila (tipo `object`); `None` si falta la clave o `tags` no es un objeto JSON."""
    return tags.map(lambda value: value.get(key) if isinstance(value, dict) else None).astype(object)


def validate_events(raw: pd.DataFrame) -> ValidationResult:
    """Separa los eventos válidos de los rechazados. `raw` tiene las columnas de `extract.COLUMNS`."""
    events_read = {event_type: 0 for event_type in SOURCE_EVENT_TYPES}
    events_read.update(raw["event_type"].value_counts().astype(int).to_dict())

    tags = raw["tags"]
    timestamp = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce", format="ISO8601")
    warehouse = _tag(tags, "warehouse")
    client_id = _tag(tags, "client_id")
    quantity = _tag(tags, "quantity")
    order_id = _tag(tags, "order_id")

    is_inbound = raw["event_type"].eq(INBOUND)
    bad_timestamp = timestamp.isna()
    bad_warehouse = ~warehouse.isin(WAREHOUSES)
    bad_client = ~client_id.map(_is_client_id).astype(bool)
    bad_quantity = is_inbound & ~quantity.map(lambda value: _is_int(value, 1)).astype(bool)

    # Duplicados: entre las filas que han pasado las reglas anteriores y en orden cronológico (llegan así de extract).
    passes = ~(bad_timestamp | bad_warehouse | bad_client | bad_quantity)
    has_order = raw["event_type"].isin(ORDER_EVENT_TYPES) & order_id.map(lambda value: _is_int(value, 1)).astype(bool)
    candidates = pd.DataFrame({"event_type": raw["event_type"], "warehouse": warehouse, "order_id": order_id})
    duplicate = pd.Series(False, index=raw.index)
    checked = passes & has_order
    if checked.any():
        duplicate.loc[checked] = candidates.loc[checked].duplicated(keep="first")

    reason = pd.Series(
        np.select(
            [bad_timestamp, bad_warehouse, bad_client, bad_quantity, duplicate],
            list(REASONS),
            default="",
        ),
        index=raw.index,
    )
    rejected_mask = reason.ne("")
    rejected: dict[str, dict[str, int]] = {}
    if rejected_mask.any():
        counts = pd.DataFrame({"event_type": raw["event_type"], "reason": reason})[rejected_mask].value_counts()
        for (event_type, why), count in sorted(counts.items()):
            rejected.setdefault(event_type, {})[why] = int(count)

    keep = ~rejected_mask
    valid = pd.DataFrame(
        {
            "id": raw["id"],
            "event_type": raw["event_type"],
            "timestamp": timestamp,
            "warehouse": warehouse,
            "client_id": client_id,
            # Solo el volumen de entrada usa la cantidad; en los demás eventos se deja a 0 para no sumarla nunca.
            "quantity": quantity.where(is_inbound, 0),
        }
    )[keep].reset_index(drop=True)
    valid["quantity"] = valid["quantity"].astype("int64")
    return ValidationResult(valid=valid[VALID_COLUMNS], events_read=events_read, rejected=rejected)
