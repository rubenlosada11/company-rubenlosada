"""Datos y utilidades de los tests del pipeline semanal (`app/reporting/`).

Los eventos se insertan directamente en `telemetry_events` de la base SQLite temporal de cada test (sin pasar por
`TelemetryEvent`), para poder probar también filas que el contrato rechazaría.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, select

# Los tipos de evento se reexportan para que los tests los importen desde aquí junto con los datos.
from app.reporting.extract import COLUMNS, DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT  # noqa: F401
from app.telemetry.storage import telemetry_engine, telemetry_events

# Semanas de referencia (lunes). «Ahora» = miércoles de la semana siguiente a W2: W1 y W2 son las 2 últimas
# completas.
W0 = datetime(2026, 10, 19, tzinfo=UTC).date()
W1 = datetime(2026, 10, 26, tzinfo=UTC).date()
W2 = datetime(2026, 11, 2, tzinfo=UTC).date()
CURRENT = datetime(2026, 11, 9, tzinfo=UTC).date()
NOW = datetime(2026, 11, 11, 9, 30, tzinfo=UTC)


def at(day, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    """Momento UTC de un día (`date`)."""
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


def event(
    event_type: str,
    timestamp: datetime,
    *,
    warehouse: str | None = "los_angeles",
    client_id: str | None = "fashion-co",
    quantity: Any = 1,
    order_id: int | None = None,
    environment: str = "development",
    tags: Any = ...,
) -> dict[str, Any]:
    """Fila de `telemetry_events`. `tags` (cualquier valor, también `None`) sustituye a las propiedades calculadas."""
    if tags is ...:
        tags = {"product_id": "SKU-1", "product_category": "fashion"}
        if warehouse is not None:
            tags["warehouse"] = warehouse
        if client_id is not None:
            tags["client_id"] = client_id
        if quantity is not None:
            tags["quantity"] = quantity
        if order_id is not None:
            tags["order_id"] = order_id
    return {
        "id": uuid.uuid4(),
        "event_type": event_type,
        "timestamp": timestamp,
        "service": "backend",
        "tags": tags,
        "session_id": None,
        "user_id": None,
        "request_id": None,
        "schema_version": "1.0.0",
        "environment": environment,
    }


def insert(*rows: dict[str, Any]) -> None:
    with telemetry_engine().begin() as connection:
        connection.execute(telemetry_events.insert(), list(rows))


def telemetry_count() -> int:
    with telemetry_engine().connect() as connection:
        return connection.execute(select(func.count()).select_from(telemetry_events)).scalar_one()


def frame(*rows: dict[str, Any]) -> pd.DataFrame:
    """DataFrame con la forma de la salida de `extract` (sin pasar por la base)."""
    return pd.DataFrame([{name: row[name] for name in COLUMNS} for row in rows], columns=COLUMNS)


def record_orders(*orders: tuple[str, str, datetime]) -> None:
    """Órdenes del inventario (fuente de verdad): `(tipo, almacén, cuándo)`; tipo `inbound`, `dispatch` o `loss`."""
    from sqlmodel import Session

    from app.database import get_engine
    from app.inventory_models import SKU, StockEntry, StockExit

    with Session(get_engine()) as session:
        sku = SKU(
            name="Camiseta",
            sku=f"SKU-{uuid.uuid4().hex[:8]}",
            client_name="Fashion Co",
            category="fashion",
            warehouse="LA",
        )
        session.add(sku)
        session.flush()
        for kind, warehouse, moment in orders:
            common = {"sku_id": sku.id, "quantity": 1, "warehouse": warehouse, "created_at": moment, "user_uuid": "u-1"}
            if kind == "inbound":
                session.add(StockEntry(reference="REF", **common))
            else:
                session.add(StockExit(exit_type=kind, **common))
        session.commit()
