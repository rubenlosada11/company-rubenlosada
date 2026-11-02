"""Schemas Pydantic de petición y respuesta del inventario (Hito 5). Contexto: `CONTEXT-gestor-inventario.es.md`.

- Petición: `SKUCreate`, `StockEntryCreate`, `StockExitCreate`. Lo que no controla el cliente (`id`, `created_at`,
  `user_uuid`) no forma parte de ellos: si llega en el cuerpo se ignora. `user_uuid` sale del token (usuario de TinyDB).
- Respuesta: `SKURead` (con `current_stock` y `stock_by_warehouse`, calculados), `StockEntryRead`, `StockExitRead` y
  los movimientos de `GET /inventory/orders` (`InboundMovement` | `OutboundMovement`, con los datos del SKU).

Los valores no válidos responden 422 (validación estándar de FastAPI) con el mensaje en español.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class Warehouse(StrEnum):
    LA = "LA"  # Los Ángeles
    ZGZ = "ZGZ"  # Zaragoza


class ProductCategory(StrEnum):
    FASHION = "fashion"
    ELECTRONICS = "electronics"
    COSMETICS = "cosmetics"


# Nombre corto del módulo. La clase se llama `ProductCategory` para que OpenAPI no la confunda con la categoría de
# proveedor (`app.models.SupplierCategory`).
Category = ProductCategory


class ExitType(StrEnum):
    DISPATCH = "dispatch"  # envío a cliente: exige `tracking_number`
    LOSS = "loss"  # discrepancia o daño confirmado: sin `tracking_number`


# Límites técnicos (no de negocio): caben en las columnas y en un `INTEGER` de PostgreSQL.
MAX_QUANTITY = 2_147_483_647

# Entero estricto: rechaza textos ("5"), decimales (5.0) y booleanos (true → 1).
Quantity = Annotated[int, Field(strict=True, gt=0, le=MAX_QUANTITY)]
SkuId = Annotated[int, Field(strict=True, gt=0)]


Text64 = Annotated[str, Field(min_length=1, max_length=64)]
Text120 = Annotated[str, Field(min_length=1, max_length=120)]
Text200 = Annotated[str, Field(min_length=1, max_length=200)]


TRACKING_REQUIRED = "tracking_number es obligatorio cuando exit_type es 'dispatch'"
TRACKING_FORBIDDEN = "tracking_number debe ser nulo cuando exit_type es 'loss'"


class _Input(BaseModel):
    # Recorta espacios: "  LA " es "LA" y un texto solo con espacios cuenta como vacío.
    model_config = ConfigDict(str_strip_whitespace=True)


class SKUCreate(_Input):
    name: Text200
    sku: Text64
    client_name: Text120
    category: Category
    warehouse: Warehouse


class StockEntryCreate(_Input):
    sku_id: SkuId
    quantity: Quantity
    reference: Text64
    # Si no se envía, el almacén en el que está registrado el SKU.
    warehouse: Warehouse | None = None


class StockExitCreate(_Input):
    sku_id: SkuId
    quantity: Quantity
    exit_type: ExitType
    # `validate_default`: la regla se comprueba también cuando el campo no se envía.
    tracking_number: str | None = Field(default=None, max_length=64, validate_default=True)
    # Si no se envía, el almacén en el que está registrado el SKU.
    warehouse: Warehouse | None = None

    @field_validator("tracking_number", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("tracking_number")
    @classmethod
    def check_tracking_number(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Regla 3: obligatorio en un `dispatch` y nulo en una `loss`."""
        exit_type = info.data.get("exit_type")  # ausente si `exit_type` ya ha fallado
        if exit_type == ExitType.DISPATCH and value is None:
            raise ValueError(TRACKING_REQUIRED)
        if exit_type == ExitType.LOSS and value is not None:
            raise ValueError(TRACKING_FORBIDDEN)
        return value


def _as_utc(value: datetime) -> datetime:
    # SQLite no guarda la zona horaria: todo `created_at` se escribe en UTC, así que se restaura al leer.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StockByWarehouse(BaseModel):
    """Stock de un SKU en cada almacén por separado (regla 6: nunca se suman)."""

    LA: int
    ZGZ: int


class SKURead(_Read):
    id: int
    name: str
    sku: str
    client_name: str
    category: Category
    warehouse: Warehouse
    # Stock en el almacén del SKU (`warehouse`) = entradas − salidas registradas en ese almacén.
    current_stock: int
    stock_by_warehouse: StockByWarehouse


class SKUSummary(_Read):
    """Datos del SKU que acompañan a cada movimiento en `GET /inventory/orders`."""

    id: int
    name: str
    sku: str
    client_name: str
    category: Category
    warehouse: Warehouse


class _MovementRead(_Read):
    @field_validator("created_at", check_fields=False)
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


# Campos en el orden de la especificación del briefing.
class StockEntryRead(_MovementRead):
    id: int
    sku_id: int
    quantity: int
    reference: str
    warehouse: Warehouse
    created_at: datetime
    user_uuid: str


class StockExitRead(_MovementRead):
    id: int
    sku_id: int
    quantity: int
    exit_type: ExitType
    tracking_number: str | None
    warehouse: Warehouse
    created_at: datetime
    user_uuid: str


class InboundMovement(StockEntryRead):
    movement_type: Literal["inbound"] = "inbound"
    sku: SKUSummary


class OutboundMovement(StockExitRead):
    movement_type: Literal["outbound"] = "outbound"
    sku: SKUSummary


Movement = Annotated[InboundMovement | OutboundMovement, Field(discriminator="movement_type")]
