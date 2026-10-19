"""`PATCH /suppliers/{id}/rate` — cambio de tarifa (API-042, TESTING.md §10).

Regla del CONTEXT (trazabilidad de tarifas): cambiar la tarifa renueva `updated_at`, y no toca ningún otro campo.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import SupplierRateUpdate
from app.routes.suppliers import create_supplier, update_rate

from .conftest import supplier_data


def new_rate(value) -> SupplierRateUpdate:
    return SupplierRateUpdate(rate_per_shipment=value)


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_rate_change_renews_updated_at_and_changes_nothing_else(clock, suppliers):
    created = create_supplier(supplier_data(notes="Contrato anual"), suppliers)
    later = clock.advance(days=3)

    result = update_rate(created.id, new_rate(8.10), suppliers)

    assert (result.rate_per_shipment, result.updated_at) == (8.10, later)
    unchanged = created.model_dump(exclude={"rate_per_shipment", "updated_at"})
    assert result.model_dump(exclude={"rate_per_shipment", "updated_at"}) == unchanged


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_smallest_positive_rate_is_accepted(clock, suppliers):
    created = create_supplier(supplier_data(), suppliers)
    assert update_rate(created.id, new_rate(0.01), suppliers).rate_per_shipment == 0.01


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -2.5, "8.10", None, False])
def test_invalid_rate_is_rejected(value):
    with pytest.raises(ValidationError):
        new_rate(value)


def test_rate_of_a_missing_supplier_is_404_and_creates_nothing(suppliers):
    with pytest.raises(HTTPException) as error:
        update_rate(7, new_rate(8.10), suppliers)
    assert (error.value.status_code, error.value.detail) == (404, "Proveedor 7 no encontrado")
    assert suppliers.all() == []
