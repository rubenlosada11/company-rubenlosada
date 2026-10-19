"""`GET /suppliers` — listado con filtros opcionales y combinables (API-042, TESTING.md §10).

`country` filtra por país y `category` devuelve los proveedores que tienen esa categoría entre las suyas (un
transportista puede tener varias). Los dos se combinan con AND.
"""

import pytest

from app.models import Category, Country
from app.routes.suppliers import create_supplier, list_suppliers

from .conftest import supplier_data


@pytest.fixture
def directory(suppliers):
    """Tres proveedores: MRW (ES, última milla), DHL (ES, última milla + internacional) y UPS (USA, internacional)."""
    for data in (
        supplier_data(),
        supplier_data(name="DHL España", categories=["carrier_last_mile", "carrier_international"]),
        supplier_data(name="UPS", country="USA", currency="USD", categories=["carrier_international"]),
    ):
        create_supplier(data, suppliers)
    return suppliers


def names(result) -> list[str]:
    return [supplier.name for supplier in result]


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_without_filters_lists_every_supplier(directory):
    assert names(list_suppliers(directory)) == ["MRW España", "DHL España", "UPS"]


def test_filter_by_country(directory):
    assert names(list_suppliers(directory, country=Country.USA)) == ["UPS"]


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_category_filter_includes_multi_category_suppliers(directory):
    assert names(list_suppliers(directory, category=Category.CARRIER_INTERNATIONAL)) == ["DHL España", "UPS"]


def test_filters_combine_with_and(directory):
    result = list_suppliers(directory, country=Country.SPAIN, category=Category.CARRIER_INTERNATIONAL)
    assert names(result) == ["DHL España"]


def test_valid_category_without_suppliers_gives_an_empty_list(directory):
    assert list_suppliers(directory, category=Category.FLEET_MAINTENANCE) == []


def test_empty_directory_gives_an_empty_list(suppliers):
    assert list_suppliers(suppliers) == []


# --- Modo de fallo ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("enum", "value"), [(Country, "France"), (Category, "catering")])
def test_only_the_values_of_the_context_are_valid_filters(enum, value):
    # FastAPI convierte el parámetro con estos enums: un valor fuera del CONTEXT nunca llega al filtro (422).
    with pytest.raises(ValueError):
        enum(value)
