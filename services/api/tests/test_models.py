from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Category, Country, Status, Supplier, SupplierCreate, SupplierRateUpdate, utc_now


def valid_payload(**overrides):
    payload = {
        "name": "UPS Ground",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 7.45,
        "currency": "USD",
        "status": "active",
        "service_zone": "West Coast",
        "contact_email": "business@ups.com",
        "notes": "Carrier principal para entregas locales en Los Ángeles y alrededores.",
    }
    payload.update(overrides)
    return payload


def error_fields(exc: ValidationError) -> list[tuple]:
    return [err["loc"] for err in exc.errors()]


def test_valid_supplier():
    supplier = SupplierCreate.model_validate(valid_payload())
    assert supplier.country is Country.USA
    assert supplier.categories == [Category.CARRIER_LAST_MILE]
    assert supplier.status is Status.ACTIVE


def test_optional_fields_can_be_omitted():
    payload = valid_payload()
    for field in ("service_zone", "contact_email", "notes"):
        payload.pop(field)
    supplier = SupplierCreate.model_validate(payload)
    assert supplier.service_zone is None and supplier.contact_email is None and supplier.notes is None


def test_blank_optional_fields_become_none():
    supplier = SupplierCreate.model_validate(valid_payload(service_zone="  ", notes=""))
    assert supplier.service_zone is None and supplier.notes is None


@pytest.mark.parametrize(
    "field", ["name", "country", "categories", "rate_per_shipment", "currency", "status"]
)
def test_required_field_missing(field):
    payload = valid_payload()
    payload.pop(field)
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(payload)
    assert (field,) in error_fields(exc.value)


def test_blank_name_rejected():
    with pytest.raises(ValidationError):
        SupplierCreate.model_validate(valid_payload(name="   "))


def test_invalid_status():
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(valid_payload(status="inactive"))
    assert ("status",) in error_fields(exc.value)


@pytest.mark.parametrize("country", ["Mexico", "usa", "España"])
def test_invalid_country(country):
    with pytest.raises(ValidationError):
        SupplierCreate.model_validate(valid_payload(country=country))


def test_invalid_category():
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(valid_payload(categories=["carrier_last_mile", "catering"]))
    assert ("categories", 1) in error_fields(exc.value)


def test_empty_categories_rejected():
    with pytest.raises(ValidationError):
        SupplierCreate.model_validate(valid_payload(categories=[]))


def test_multiple_categories_and_duplicates_removed():
    supplier = SupplierCreate.model_validate(
        valid_payload(categories=["carrier_last_mile", "carrier_international", "carrier_last_mile"])
    )
    assert supplier.categories == [Category.CARRIER_LAST_MILE, Category.CARRIER_INTERNATIONAL]


@pytest.mark.parametrize("rate", [0, 0.0, -1, -7.45, "7.45", True, float("inf"), float("nan")])
def test_invalid_rate(rate):
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(valid_payload(rate_per_shipment=rate))
    assert ("rate_per_shipment",) in error_fields(exc.value)


@pytest.mark.parametrize("rate", [0, -3.2])
def test_rate_update_rejects_non_positive(rate):
    with pytest.raises(ValidationError):
        SupplierRateUpdate.model_validate({"rate_per_shipment": rate})


def test_rate_update_accepts_integer():
    assert SupplierRateUpdate.model_validate({"rate_per_shipment": 8}).rate_per_shipment == 8.0


@pytest.mark.parametrize(("country", "currency"), [("USA", "EUR"), ("Spain", "USD")])
def test_currency_must_match_country(country, currency):
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(valid_payload(country=country, currency=currency))
    assert "debe usar la moneda" in str(exc.value)


def test_spain_with_eur_is_valid():
    supplier = SupplierCreate.model_validate(
        valid_payload(name="SEUR", country="Spain", currency="EUR", rate_per_shipment=5.2)
    )
    assert supplier.currency == "EUR"


@pytest.mark.parametrize("email", ["business-ups.com", "a@b", "a b@ups.com", "@ups.com"])
def test_invalid_email(email):
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate(valid_payload(contact_email=email))
    assert ("contact_email",) in error_fields(exc.value)


def test_client_cannot_set_server_fields():
    supplier = SupplierCreate.model_validate(
        valid_payload(id=999, updated_at="2000-01-01T00:00:00Z")
    )
    dumped = supplier.model_dump()
    assert "updated_at" not in dumped and "id" not in dumped


def test_server_timestamp_is_utc_now():
    before = datetime.now(UTC)
    stamp = utc_now()
    after = datetime.now(UTC)
    assert stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0
    assert before <= stamp <= after


def test_supplier_response_model_includes_server_fields():
    stamp = utc_now()
    supplier = Supplier.model_validate({**valid_payload(), "id": 1, "updated_at": stamp.isoformat()})
    assert supplier.id == 1 and supplier.updated_at == stamp
