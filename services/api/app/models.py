"""Modelos Pydantic del directorio de proveedores.

Fuente de verdad de campos, categorías, estados y reglas: `CONTEXT-directorio.md` (raíz del repo).
"""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Country(StrEnum):
    USA = "USA"
    SPAIN = "Spain"


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"


class Category(StrEnum):
    CARRIER_LAST_MILE = "carrier_last_mile"
    CARRIER_INTERNATIONAL = "carrier_international"
    WAREHOUSE_SUPPLIES = "warehouse_supplies"
    PACKAGING_MATERIALS = "packaging_materials"
    REVERSE_LOGISTICS = "reverse_logistics"
    FLEET_MAINTENANCE = "fleet_maintenance"
    IT_AND_WMS_SOFTWARE = "it_and_wms_software"
    CLEANING_AND_FACILITIES = "cleaning_and_facilities"


class Status(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


# Restricción de negocio del CONTEXT: la moneda del contrato la fija el país.
CURRENCY_BY_COUNTRY: dict[Country, Currency] = {
    Country.USA: Currency.USD,
    Country.SPAIN: Currency.EUR,
}

# Validación básica (sin dependencias): algo@dominio.tld, sin espacios.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# `strict`: acepta números JSON (enteros o decimales) y rechaza textos ("7.45") y booleanos (true → 1.0).
Rate = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


def utc_now() -> datetime:
    """Timestamp del servidor para `updated_at` (el cliente nunca lo envía)."""
    return datetime.now(UTC)


class SupplierCreate(BaseModel):
    """Datos que controla el cliente al registrar un proveedor.

    `id` y `updated_at` no forman parte del modelo: si el cliente los envía se ignoran.
    """

    model_config = {"str_strip_whitespace": True}

    name: NonEmptyStr
    country: Country
    categories: Annotated[list[Category], Field(min_length=1)]
    rate_per_shipment: Rate
    currency: Currency
    status: Status
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    @field_validator("service_zone", "contact_email", "notes", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("categories")
    @classmethod
    def dedupe_categories(cls, value: list[Category]) -> list[Category]:
        return list(dict.fromkeys(value))

    @field_validator("contact_email")
    @classmethod
    def check_email(cls, value: str | None) -> str | None:
        if value is not None and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("contact_email no tiene un formato de email válido")
        return value

    @model_validator(mode="after")
    def check_currency_matches_country(self) -> "SupplierCreate":
        expected = CURRENCY_BY_COUNTRY[self.country]
        if self.currency != expected:
            raise ValueError(
                f"Un proveedor de {self.country.value} debe usar la moneda {expected.value} "
                f"(recibido: {self.currency.value})"
            )
        return self


class SupplierRateUpdate(BaseModel):
    rate_per_shipment: Rate


class SupplierStatusUpdate(BaseModel):
    status: Status


class Supplier(SupplierCreate):
    """Proveedor tal y como lo devuelve la API: datos del cliente + campos del servidor."""

    id: int
    updated_at: datetime
