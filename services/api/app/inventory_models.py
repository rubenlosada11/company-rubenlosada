"""Tablas SQLModel del inventario (Hito 5): `SKU`, `StockEntry` y `StockExit`.

Fuente de verdad: `CONTEXT-gestor-inventario.es.md` (raíz del repo). Nombres de entidades y campos exactos del
briefing. Aquí solo está lo que se guarda: la validación de lo que llega por la API vive en `app/inventory_schemas.py`.

- `current_stock` **no** es una columna: se calcula siempre a partir de los movimientos (`app/services/inventory.py`).
- `user_uuid` es el UUID de un usuario de TinyDB (`db/auth.json`). No hay modelo `User` en SQL ni clave foránea hacia
  él: los usuarios viven solo en TinyDB.
- `warehouse` (`"LA"` o `"ZGZ"`) está en las tres tablas: los dos almacenes comparten tablas.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Momento de creación de un movimiento (lo pone el servidor, nunca el cliente)."""
    return datetime.now(UTC)


def _created_at_column() -> Column:
    # Con zona horaria: en PostgreSQL es `timestamptz`. SQLite la pierde al leer; los schemas la restauran (UTC).
    return Column(DateTime(timezone=True), nullable=False, index=True)


class SKU(SQLModel, table=True):
    """Producto de una marca cliente registrado en un almacén (equivale a `Product` del README del proyecto)."""

    __tablename__ = "skus"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    # Código asignado por el cliente. Único: identifica el SKU en los mensajes de error («Insufficient stock…»).
    sku: str = Field(max_length=64, unique=True, index=True)
    client_name: str = Field(max_length=120)
    category: str = Field(max_length=20)
    # Almacén en el que está registrado el SKU; su `current_stock` es el de este almacén.
    warehouse: str = Field(max_length=3, index=True)


class StockEntry(SQLModel, table=True):
    """Recepción de mercancía de una marca cliente en un almacén (equivale a `InboundOrder`)."""

    __tablename__ = "stock_entries"

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="skus.id", index=True)
    quantity: int
    reference: str = Field(max_length=64)
    warehouse: str = Field(max_length=3, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_column=_created_at_column())
    user_uuid: str = Field(max_length=36)


class StockExit(SQLModel, table=True):
    """Despacho a un cliente (`dispatch`) o baja por pérdida (`loss`) (equivale a `OutboundOrder`)."""

    __tablename__ = "stock_exits"

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="skus.id", index=True)
    quantity: int
    exit_type: str = Field(max_length=10)
    tracking_number: str | None = Field(default=None, max_length=64)
    warehouse: str = Field(max_length=3, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_column=_created_at_column())
    user_uuid: str = Field(max_length=36)
