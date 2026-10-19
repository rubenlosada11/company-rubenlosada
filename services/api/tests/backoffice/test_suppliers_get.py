"""`GET /suppliers/{id}` — consulta de un proveedor (API-042, TESTING.md §10)."""

import pytest
from fastapi import HTTPException

from app.routes.suppliers import create_supplier, get_supplier

from .conftest import supplier_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_get_returns_the_supplier_with_its_id(suppliers):
    created = create_supplier(supplier_data(), suppliers)
    assert get_supplier(created.id, suppliers) == created


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_each_id_returns_its_own_supplier(suppliers):
    first = create_supplier(supplier_data(), suppliers)
    second = create_supplier(supplier_data(name="SEUR"), suppliers)
    assert (get_supplier(first.id, suppliers).name, get_supplier(second.id, suppliers).name) == ("MRW España", "SEUR")


# --- Modo de fallo ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("supplier_id", [99, 0, -1])
def test_missing_supplier_is_404_with_its_id_in_the_message(suppliers, supplier_id):
    create_supplier(supplier_data(), suppliers)
    with pytest.raises(HTTPException) as error:
        get_supplier(supplier_id, suppliers)
    assert (error.value.status_code, error.value.detail) == (404, f"Proveedor {supplier_id} no encontrado")
