import json
import os
import subprocess
import sys
import time
from datetime import datetime

import pytest

from app.seed import SUPPLIERS_SEED

NEW_SUPPLIER = {
    "name": "Transportes Ebro",
    "country": "Spain",
    "categories": ["carrier_last_mile"],
    "rate_per_shipment": 3.95,
    "currency": "EUR",
    "status": "active",
    "service_zone": "Aragón",
    "contact_email": "ops@transportes-ebro.es",
}

# Ids del seed (orden de SUPPLIERS_SEED): 1 = UPS Ground, 5 = Laser Ship (suspended), 8 = MRW España.
UPS, LASER_SHIP, MRW = 1, 5, 8


def names(response):
    return [supplier["name"] for supplier in response.json()]


def context_names(**criteria):
    """Nombres esperados calculados directamente sobre los datos del CONTEXT."""
    return [
        s["name"]
        for s in SUPPLIERS_SEED
        if all(
            value in s["categories"] if field == "category" else s[field] == value
            for field, value in criteria.items()
        )
    ]


def error_locations(response):
    return [tuple(err["loc"]) for err in response.json()["detail"]]


# --- POST /suppliers ---------------------------------------------------------------------------------------


def test_create_supplier(client):
    response = client.post("/suppliers", json=NEW_SUPPLIER)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert {k: body[k] for k in NEW_SUPPLIER} == NEW_SUPPLIER
    assert body["notes"] is None
    assert client.get("/suppliers/1").json() == body


def test_create_generates_server_timestamp(client):
    before = datetime.now().astimezone()
    body = client.post("/suppliers", json=NEW_SUPPLIER).json()
    stamp = datetime.fromisoformat(body["updated_at"])
    assert stamp.utcoffset().total_seconds() == 0
    assert before <= stamp <= datetime.now().astimezone()


def test_create_ignores_client_id_and_timestamp(client):
    payload = {**NEW_SUPPLIER, "id": 999, "updated_at": "2000-01-01T00:00:00Z"}
    body = client.post("/suppliers", json=payload).json()
    assert body["id"] == 1
    assert not body["updated_at"].startswith("2000")


def test_created_ids_are_assigned_by_tinydb(seeded_client):
    assert seeded_client.post("/suppliers", json=NEW_SUPPLIER).json()["id"] == 16


@pytest.mark.parametrize(
    ("override", "location"),
    [
        ({"status": "inactive"}, ("body", "status")),
        ({"rate_per_shipment": 0}, ("body", "rate_per_shipment")),
        ({"rate_per_shipment": -3.95}, ("body", "rate_per_shipment")),
        ({"country": "Portugal"}, ("body", "country")),
        ({"categories": []}, ("body", "categories")),
        ({"categories": ["catering"]}, ("body", "categories", 0)),
        ({"contact_email": "ops-ebro"}, ("body", "contact_email")),
        ({"currency": "USD"}, ("body",)),
    ],
)
def test_create_rejects_invalid_data_with_422(client, override, location):
    response = client.post("/suppliers", json={**NEW_SUPPLIER, **override})
    assert response.status_code == 422
    assert location in error_locations(response)
    assert client.get("/suppliers").json() == []  # nada llegó a TinyDB


@pytest.mark.parametrize("field", ["name", "country", "categories", "rate_per_shipment", "currency", "status"])
def test_create_rejects_missing_required_field(client, field):
    payload = {k: v for k, v in NEW_SUPPLIER.items() if k != field}
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422
    assert ("body", field) in error_locations(response)


def test_create_rejects_currency_inconsistent_with_country(client):
    response = client.post("/suppliers", json={**NEW_SUPPLIER, "currency": "USD"})
    assert "debe usar la moneda EUR" in response.json()["detail"][0]["msg"]


# --- GET /suppliers -----------------------------------------------------------------------------------------


def test_list_empty(client):
    response = client.get("/suppliers")
    assert response.status_code == 200 and response.json() == []


def test_list_all(seeded_client):
    response = seeded_client.get("/suppliers")
    assert response.status_code == 200
    assert names(response) == context_names()
    assert [s["id"] for s in response.json()] == list(range(1, 16))


@pytest.mark.parametrize("country", ["USA", "Spain"])
def test_filter_by_country(seeded_client, country):
    response = seeded_client.get("/suppliers", params={"country": country})
    assert response.status_code == 200
    assert names(response) == context_names(country=country)
    assert all(s["country"] == country for s in response.json())


def test_filter_by_country_spain_has_six(seeded_client):
    assert len(seeded_client.get("/suppliers?country=Spain").json()) == 6


@pytest.mark.parametrize(
    "category", ["carrier_last_mile", "carrier_international", "reverse_logistics", "packaging_materials"]
)
def test_filter_by_category(seeded_client, category):
    response = seeded_client.get("/suppliers", params={"category": category})
    assert names(response) == context_names(category=category)
    assert all(category in s["categories"] for s in response.json())


def test_filter_by_category_includes_multi_category_carriers(seeded_client):
    response = seeded_client.get("/suppliers?category=carrier_international")
    assert names(response) == ["DHL Express USA", "DHL Express España"]


def test_filter_by_valid_category_without_suppliers(seeded_client):
    response = seeded_client.get("/suppliers?category=fleet_maintenance")
    assert response.status_code == 200 and response.json() == []


def test_combined_filters(seeded_client):
    response = seeded_client.get("/suppliers", params={"country": "Spain", "category": "carrier_last_mile"})
    assert names(response) == ["MRW España", "SEUR", "DHL Express España", "Nacex"]
    assert names(response) == context_names(country="Spain", category="carrier_last_mile")


@pytest.mark.parametrize("query", ["country=Mexico", "country=usa", "category=catering"])
def test_invalid_filter_value_returns_422(seeded_client, query):
    assert seeded_client.get(f"/suppliers?{query}").status_code == 422


# --- GET /suppliers/{id} ------------------------------------------------------------------------------------


def test_get_supplier_by_id(seeded_client):
    response = seeded_client.get(f"/suppliers/{MRW}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == MRW and body["name"] == "MRW España" and body["currency"] == "EUR"


@pytest.mark.parametrize("supplier_id", [0, 16, 999])
def test_get_missing_supplier_returns_404(seeded_client, supplier_id):
    response = seeded_client.get(f"/suppliers/{supplier_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": f"Proveedor {supplier_id} no encontrado"}


def test_get_non_numeric_id_returns_422(seeded_client):
    assert seeded_client.get("/suppliers/abc").status_code == 422


# --- PATCH /suppliers/{id}/rate -----------------------------------------------------------------------------


def test_update_rate(seeded_client):
    response = seeded_client.patch(f"/suppliers/{UPS}/rate", json={"rate_per_shipment": 7.99})
    assert response.status_code == 200
    assert response.json()["rate_per_shipment"] == 7.99
    assert seeded_client.get(f"/suppliers/{UPS}").json()["rate_per_shipment"] == 7.99


def test_update_rate_refreshes_updated_at(seeded_client):
    before = seeded_client.get(f"/suppliers/{UPS}").json()["updated_at"]
    time.sleep(0.01)
    after = seeded_client.patch(f"/suppliers/{UPS}/rate", json={"rate_per_shipment": 7.99}).json()["updated_at"]
    assert datetime.fromisoformat(after) > datetime.fromisoformat(before)
    assert seeded_client.get(f"/suppliers/{UPS}").json()["updated_at"] == after  # persistido


def test_update_rate_ignores_client_timestamp(seeded_client):
    body = seeded_client.patch(
        f"/suppliers/{UPS}/rate", json={"rate_per_shipment": 8, "updated_at": "2000-01-01T00:00:00Z"}
    ).json()
    assert body["rate_per_shipment"] == 8.0
    assert not body["updated_at"].startswith("2000")


def test_update_rate_only_changes_rate_and_timestamp(seeded_client):
    before = seeded_client.get(f"/suppliers/{UPS}").json()
    after = seeded_client.patch(f"/suppliers/{UPS}/rate", json={"rate_per_shipment": 7.99}).json()
    unchanged = {k: v for k, v in before.items() if k not in ("rate_per_shipment", "updated_at")}
    assert {k: after[k] for k in unchanged} == unchanged


@pytest.mark.parametrize("rate", [0, -1, -7.45, "8", True, None])
def test_update_rate_rejects_invalid_values(seeded_client, rate):
    response = seeded_client.patch(f"/suppliers/{UPS}/rate", json={"rate_per_shipment": rate})
    assert response.status_code == 422
    assert seeded_client.get(f"/suppliers/{UPS}").json()["rate_per_shipment"] == 7.45


def test_update_rate_missing_supplier_returns_404(seeded_client):
    assert seeded_client.patch("/suppliers/999/rate", json={"rate_per_shipment": 8}).status_code == 404


# --- PATCH /suppliers/{id}/status ---------------------------------------------------------------------------


def test_update_status(seeded_client):
    response = seeded_client.patch(f"/suppliers/{LASER_SHIP}/status", json={"status": "active"})
    assert response.status_code == 200 and response.json()["status"] == "active"
    response = seeded_client.patch(f"/suppliers/{UPS}/status", json={"status": "suspended"})
    assert response.json()["status"] == "suspended"
    assert seeded_client.get(f"/suppliers/{UPS}").json()["status"] == "suspended"


def test_update_status_keeps_rate_timestamp(seeded_client):
    before = seeded_client.get(f"/suppliers/{UPS}").json()
    after = seeded_client.patch(f"/suppliers/{UPS}/status", json={"status": "suspended"}).json()
    assert after["updated_at"] == before["updated_at"]


@pytest.mark.parametrize("value", ["inactive", "Active", "", None])
def test_update_status_rejects_invalid_values(seeded_client, value):
    response = seeded_client.patch(f"/suppliers/{UPS}/status", json={"status": value})
    assert response.status_code == 422
    assert seeded_client.get(f"/suppliers/{UPS}").json()["status"] == "active"


def test_update_status_missing_supplier_returns_404(seeded_client):
    assert seeded_client.patch("/suppliers/999/status", json={"status": "active"}).status_code == 404


# --- DELETE /suppliers/{id} ---------------------------------------------------------------------------------


def test_delete_supplier(seeded_client):
    response = seeded_client.delete(f"/suppliers/{MRW}")
    assert response.status_code == 204 and response.content == b""
    assert seeded_client.get(f"/suppliers/{MRW}").status_code == 404
    assert len(seeded_client.get("/suppliers").json()) == 14


def test_delete_missing_supplier_returns_404(seeded_client):
    assert seeded_client.delete("/suppliers/999").status_code == 404
    seeded_client.delete(f"/suppliers/{MRW}")
    assert seeded_client.delete(f"/suppliers/{MRW}").status_code == 404


# --- Persistencia y CORS ------------------------------------------------------------------------------------


def test_data_survives_api_restart(client, db_path):
    """Otro proceso con una instancia nueva de la API lee lo creado y modificado en este."""
    created = client.post("/suppliers", json=NEW_SUPPLIER).json()
    updated = client.patch(f"/suppliers/{created['id']}/rate", json={"rate_per_shipment": 4.1}).json()
    code = (
        "import sys; from fastapi.testclient import TestClient; from app.main import app\n"
        f"r = TestClient(app).get('/suppliers/{created['id']}')\n"
        "sys.stdout.buffer.write(r.content)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=True,
        env={**os.environ, "SUPPLIERS_DB_PATH": str(db_path)},
    )
    assert json.loads(result.stdout) == updated


def test_cors_allows_backoffice_origin(client):
    response = client.options(
        "/suppliers/1/rate",
        headers={"Origin": "http://localhost:3002", "Access-Control-Request-Method": "PATCH"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3002"


def test_cors_rejects_other_origins(client):
    response = client.options(
        "/suppliers", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in response.headers
