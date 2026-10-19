"""`POST /suppliers` — alta de un proveedor (API-042, TESTING.md §10).

Reglas de `CONTEXT-directorio.md` en `SupplierCreate`: la moneda la fija el país, la tarifa es un número > 0 (sin
textos ni booleanos), al menos una categoría y sin repetidas, email con formato básico. El servidor asigna `id` y
`updated_at`. Se llama a la función del router con la tabla real del TinyDB temporal.
"""

import pytest
from pydantic import ValidationError

from app.routes.suppliers import create_supplier

from .conftest import T0, supplier_data


# --- Camino feliz -------------------------------------------------------------------------------------------------


def test_create_stores_the_supplier_with_server_id_and_timestamp(clock, suppliers):
    result = create_supplier(supplier_data(service_zone="Zaragoza", contact_email="ops@mrw.test"), suppliers)

    assert result.id == 1 and result.updated_at == T0
    assert (result.name, result.country, result.currency, result.rate_per_shipment) == (
        "MRW España", "Spain", "EUR", 7.45,
    )
    assert suppliers.get(doc_id=result.id)["contact_email"] == "ops@mrw.test"


def test_client_cannot_choose_id_or_timestamp(clock, suppliers):
    result = create_supplier(supplier_data(id=99, updated_at="2000-01-01T00:00:00Z"), suppliers)
    assert (result.id, result.updated_at) == (1, T0)


# --- Casos límite -------------------------------------------------------------------------------------------------


def test_smallest_positive_rate_and_texts_are_normalized(suppliers):
    result = create_supplier(
        supplier_data(
            name="  UPS  ",
            country="USA",
            currency="USD",
            rate_per_shipment=0.01,
            categories=["carrier_last_mile", "carrier_international", "carrier_last_mile"],
            service_zone="   ",
            notes="",
        ),
        suppliers,
    )
    assert result.name == "UPS" and result.rate_per_shipment == 0.01
    assert result.categories == ["carrier_last_mile", "carrier_international"]  # sin repetidas, en su orden
    assert (result.service_zone, result.notes) == (None, None)


# --- Modos de fallo -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("country", "currency"), [("Spain", "USD"), ("USA", "EUR")], ids=["españa-en-dolares", "usa-en-euros"]
)
def test_currency_must_match_the_country(country, currency):
    with pytest.raises(ValidationError) as error:
        supplier_data(country=country, currency=currency)
    assert f"Un proveedor de {country} debe usar la moneda" in str(error.value)


@pytest.mark.parametrize("rate", [0, -1, "7.45", True, float("inf"), float("nan")])
def test_rate_must_be_a_real_positive_number(rate):
    with pytest.raises(ValidationError):
        supplier_data(rate_per_shipment=rate)


@pytest.mark.parametrize(
    ("field", "value"),
    [("name", "   "), ("categories", []), ("categories", ["catering"]), ("contact_email", "ops@mrw"), ("country", "France")],
    ids=["nombre-vacio", "sin-categorias", "categoria-inexistente", "email", "pais"],
)
def test_invalid_data_is_rejected_before_storing_anything(suppliers, field, value):
    with pytest.raises(ValidationError):
        supplier_data(**{field: value})
    assert suppliers.all() == []
