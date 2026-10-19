"""`PATCH /suppliers/{id}/status` — activar o suspender (API-042, TESTING.md §10).

Regla del CONTEXT: el flujo habitual es suspender (no borrar). `updated_at` es la fecha de la última tarifa, así que
cambiar el estado no lo toca.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Status, SupplierStatusUpdate
from app.routes.suppliers import create_supplier, update_status

from .conftest import T0, supplier_data


def to(status: str) -> SupplierStatusUpdate:
    return SupplierStatusUpdate(status=status)


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_suspending_keeps_the_rate_timestamp(clock, suppliers):
    created = create_supplier(supplier_data(), suppliers)
    clock.advance(days=10)

    result = update_status(created.id, to("suspended"), suppliers)

    assert result.status == Status.SUSPENDED
    assert result.updated_at == T0
    assert result.rate_per_shipment == created.rate_per_shipment


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_reactivating_and_repeating_the_same_status_are_allowed(suppliers):
    created = create_supplier(supplier_data(status="suspended"), suppliers)
    assert update_status(created.id, to("active"), suppliers).status == Status.ACTIVE
    assert update_status(created.id, to("active"), suppliers).status == Status.ACTIVE


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["deleted", "ACTIVE", ""])
def test_only_active_and_suspended_are_valid(value):
    with pytest.raises(ValidationError):
        to(value)


def test_status_of_a_missing_supplier_is_404(suppliers):
    with pytest.raises(HTTPException) as error:
        update_status(3, to("suspended"), suppliers)
    assert (error.value.status_code, error.value.detail) == (404, "Proveedor 3 no encontrado")
