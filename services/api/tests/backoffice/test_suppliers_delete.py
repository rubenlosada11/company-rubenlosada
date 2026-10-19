"""`DELETE /suppliers/{id}` — borrado de un proveedor (API-042, TESTING.md §10).

El backoffice no ofrece borrar (el flujo es suspender), pero la API sí lo admite.
"""

import pytest
from fastapi import HTTPException

from app.routes.suppliers import create_supplier, delete_supplier, get_supplier

from .conftest import supplier_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_deleted_supplier_is_gone(suppliers):
    created = create_supplier(supplier_data(), suppliers)
    delete_supplier(created.id, suppliers)
    with pytest.raises(HTTPException) as error:
        get_supplier(created.id, suppliers)
    assert error.value.status_code == 404


# --- Caso límite --------------------------------------------------------------------------------------------------


def test_deleting_one_supplier_leaves_the_others_untouched(suppliers):
    first = create_supplier(supplier_data(), suppliers)
    second = create_supplier(supplier_data(name="SEUR"), suppliers)
    delete_supplier(first.id, suppliers)
    assert [doc["name"] for doc in suppliers.all()] == ["SEUR"]
    assert get_supplier(second.id, suppliers) == second


# --- Modos de fallo -----------------------------------------------------------------------------------------------


def test_deleting_a_missing_supplier_is_404(suppliers):
    with pytest.raises(HTTPException) as error:
        delete_supplier(42, suppliers)
    assert (error.value.status_code, error.value.detail) == (404, "Proveedor 42 no encontrado")


def test_deleting_twice_is_404_the_second_time(suppliers):
    created = create_supplier(supplier_data(), suppliers)
    delete_supplier(created.id, suppliers)
    with pytest.raises(HTTPException) as error:
        delete_supplier(created.id, suppliers)
    assert error.value.status_code == 404
