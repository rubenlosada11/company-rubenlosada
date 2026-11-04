"""Caché de los endpoints de lectura (`CACHING_REPORT.md`): `GET /api/incidents/summary` y `GET /inventory/products`.

Por cada uno: primera petición = fallo, segunda = acierto; parámetros distintos = entradas distintas; toda escritura
correcta invalida y una rechazada no; un cambio hecho fuera de la API (escritura directa en la base) se ve al
cumplirse el TTL; la autenticación se comprueba antes de leer la caché y un error de la base no se cachea.

Ejecutar desde services/api: uv run pytest tests/test_api_cache.py
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth_models import Role
from app.database import get_engine, incidents_table, suppliers_table
from app.incident_models import IncidentRecord
from app.inventory_models import StockEntry
from app.main import app
from app.services import incidents as incidents_service
from app.services import inventory as inventory_service
from app.services.incidents import insert_incident
from tests.conftest import bearer


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    """Reloj controlado en las dos cachés: los tests adelantan el tiempo sin esperar al TTL."""
    fake = FakeClock()
    for cache in (incidents_service.summary_cache, inventory_service.products_cache):
        monkeypatch.setattr(cache, "clock", fake)
    return fake


def stats(cache):
    current = cache.stats()
    return current.hits, current.misses


# --- GET /api/incidents/summary -------------------------------------------------------------------------------------

SUMMARY_URL = "/api/incidents/summary"
SUMMARY = incidents_service.summary_cache
INCIDENT = {
    "title": "Paquete perdido",
    "description": "El cliente no ha recibido el envío.",
    "category": "lost_parcel",
    "origin": "customer",
    "branch": "central",
}


def store_incident(status: str = "open") -> int:
    """Escritura directa en TinyDB, fuera de la API (como el seed de incidencias)."""
    now = datetime.now(UTC)
    record = IncidentRecord(**INCIDENT, status=status, created_at=now, updated_at=now)
    with incidents_table() as table:
        return insert_incident(table, record)


def test_summary_second_request_is_a_hit(client):
    store_incident()
    assert client.get(SUMMARY_URL).json()["total"] == 1
    assert client.get(SUMMARY_URL).json()["total"] == 1
    assert stats(SUMMARY) == (1, 1)


def test_summary_is_invalidated_by_a_new_incident(client):
    assert client.get(SUMMARY_URL).json()["total"] == 0
    assert client.post("/api/incidents", json=INCIDENT).status_code == 201
    body = client.get(SUMMARY_URL).json()
    assert (body["total"], body["by_status"]["open"]) == (1, 1)


def test_summary_is_invalidated_by_a_status_change(client):
    incident_id = store_incident()
    assert client.get(SUMMARY_URL).json()["by_status"]["in_progress"] == 0
    assert client.patch(f"/api/incidents/{incident_id}/status", json={"status": "in_progress"}).status_code == 200
    assert client.get(SUMMARY_URL).json()["by_status"]["in_progress"] == 1


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/incidents/1/status", {"status": "resolved"}, 400),  # open → resolved no está permitida
        ("/api/incidents/999/status", {"status": "in_progress"}, 404),
        ("/api/incidents", {**INCIDENT, "title": ""}, 400),
    ],
)
def test_summary_rejected_writes_do_not_invalidate(client, path, body, status):
    store_incident()
    client.get(SUMMARY_URL)
    method = "patch" if path.endswith("/status") else "post"
    assert client.request(method, path, json=body).status_code == status
    assert SUMMARY.stats().invalidations == 0


def test_summary_out_of_band_change_is_visible_when_the_ttl_expires(client, clock):
    assert client.get(SUMMARY_URL).json()["total"] == 0
    store_incident()
    clock.advance(incidents_service.SUMMARY_TTL_SECONDS - 1)
    assert client.get(SUMMARY_URL).json()["total"] == 0
    clock.advance(1)
    assert client.get(SUMMARY_URL).json()["total"] == 1


def test_summary_requires_authentication_even_with_a_warm_cache(client, anon_client):
    client.get(SUMMARY_URL)  # caché caliente
    assert anon_client.get(SUMMARY_URL).status_code == 401
    assert anon_client.get(SUMMARY_URL, headers={"Authorization": "Bearer no-es-un-token"}).status_code == 401
    assert stats(SUMMARY) == (0, 1)  # los 401 no llegaron a leer la caché


def test_summary_is_the_same_for_every_role(client, make_user):
    """El resumen no depende de quién lo pide: compartir la entrada entre usuarios no filtra nada privado."""
    store_incident()
    admin = TestClient(app, headers=bearer(make_user("admin@trackflow.test", Role.ADMIN)))
    assert admin.get(SUMMARY_URL).content == client.get(SUMMARY_URL).content
    assert stats(SUMMARY) == (1, 1)


def test_summary_cache_key_includes_the_data_source(client, tmp_path, monkeypatch):
    """Dos bases distintas (p. ej. tras cambiar `INCIDENTS_DB_PATH`) nunca comparten entrada."""
    store_incident()
    assert client.get(SUMMARY_URL).json()["total"] == 1
    monkeypatch.setenv("INCIDENTS_DB_PATH", str(tmp_path / "otra" / "incidents.json"))
    assert client.get(SUMMARY_URL).json()["total"] == 0


def test_summary_error_is_not_cached(client, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(incidents_service, "summarize", lambda: 1 / 0)
        assert client.get(SUMMARY_URL).status_code == 500
    assert client.get(SUMMARY_URL).status_code == 200
    assert stats(SUMMARY) == (0, 2)


# --- GET /inventory/products ----------------------------------------------------------------------------------------

PRODUCTS = inventory_service.products_cache
SKU = {"name": "Camiseta básica", "sku": "CACHE-TEE-01", "client_name": "Marca", "category": "fashion", "warehouse": "LA"}


@pytest.fixture
def inventory(make_user):
    return TestClient(app, headers=bearer(make_user("almacen@trackflow.test")))


@pytest.fixture
def sku_id(inventory) -> int:
    sku = inventory.post("/inventory/products", json=SKU).json()
    assert inventory.post(
        "/inventory/orders/inbound", json={"sku_id": sku["id"], "quantity": 10, "reference": "PO-1"}
    ).status_code == 201
    PRODUCTS.reset()
    return sku["id"]


def stock_in_list(inventory, sku_id: int, **params) -> int:
    products = inventory.get("/inventory/products", params=params).json()
    return next(product["current_stock"] for product in products if product["id"] == sku_id)


def test_products_second_request_is_a_hit(inventory, sku_id):
    first = inventory.get("/inventory/products")
    assert first.content == inventory.get("/inventory/products").content
    assert stats(PRODUCTS) == (1, 1)


def test_products_warehouse_filter_has_its_own_entry(inventory, sku_id):
    inventory.post("/inventory/products", json={**SKU, "sku": "CACHE-TEE-ZGZ", "warehouse": "ZGZ"})
    PRODUCTS.reset()
    assert [p["warehouse"] for p in inventory.get("/inventory/products", params={"warehouse": "LA"}).json()] == ["LA"]
    assert [p["warehouse"] for p in inventory.get("/inventory/products", params={"warehouse": "ZGZ"}).json()] == [
        "ZGZ"
    ]
    assert len(inventory.get("/inventory/products").json()) == 2
    assert stats(PRODUCTS) == (0, 3)


@pytest.mark.parametrize(
    ("path", "body", "expected_stock"),
    [
        ("/inventory/orders/inbound", {"quantity": 5, "reference": "PO-2"}, 15),
        ("/inventory/orders/outbound", {"quantity": 4, "exit_type": "loss"}, 6),
    ],
)
def test_products_stock_movements_invalidate(inventory, sku_id, path, body, expected_stock):
    assert stock_in_list(inventory, sku_id) == 10
    assert inventory.post(path, json={"sku_id": sku_id, **body}).status_code == 201
    assert stock_in_list(inventory, sku_id) == expected_stock


def test_products_new_sku_invalidates(inventory, sku_id):
    assert len(inventory.get("/inventory/products").json()) == 1
    assert inventory.post("/inventory/products", json={**SKU, "sku": "CACHE-TEE-02"}).status_code == 201
    assert len(inventory.get("/inventory/products").json()) == 2


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/inventory/orders/outbound", {"quantity": 11, "exit_type": "loss"}, 400),  # stock insuficiente
        ("/inventory/orders/inbound", {"quantity": 0, "reference": "PO-3"}, 422),
        ("/inventory/products", {**SKU, "sku": "cache-tee-01"}, 409),  # duplicado
    ],
)
def test_products_rejected_writes_do_not_invalidate(inventory, sku_id, path, body, status):
    inventory.get("/inventory/products")
    payload = body if path == "/inventory/products" else {"sku_id": sku_id, **body}
    assert inventory.post(path, json=payload).status_code == status
    assert PRODUCTS.stats().invalidations == 0


def test_products_out_of_band_change_waits_for_the_ttl_but_the_detail_is_always_fresh(inventory, sku_id, clock):
    """Un movimiento escrito por otro proceso: el listado tarda hasta el TTL; la ficha del SKU (que usan los
    formularios para comprobar el stock antes de enviar) no está cacheada y lo ve al momento."""
    assert stock_in_list(inventory, sku_id) == 10
    with Session(get_engine()) as session:
        session.add(StockEntry(sku_id=sku_id, quantity=7, reference="EXT-1", warehouse="LA", user_uuid="externo"))
        session.commit()

    assert inventory.get(f"/inventory/products/{sku_id}").json()["current_stock"] == 17
    clock.advance(inventory_service.PRODUCTS_TTL_SECONDS - 1)
    assert stock_in_list(inventory, sku_id) == 10
    clock.advance(1)
    assert stock_in_list(inventory, sku_id) == 17


def test_products_exit_check_never_uses_the_cache(inventory, sku_id):
    """Regla 2: la comprobación de stock de una salida lee la base aunque el listado esté en caché."""
    assert stock_in_list(inventory, sku_id) == 10
    with Session(get_engine()) as session:
        session.add(StockEntry(sku_id=sku_id, quantity=5, reference="EXT-2", warehouse="LA", user_uuid="externo"))
        session.commit()
    exit_body = {"sku_id": sku_id, "quantity": 15, "exit_type": "loss"}
    assert inventory.post("/inventory/orders/outbound", json=exit_body).status_code == 201


def test_products_require_authentication_even_with_a_warm_cache(inventory, sku_id, anon_client):
    inventory.get("/inventory/products")
    assert anon_client.get("/inventory/products").status_code == 401


def test_products_database_error_is_a_500_and_is_not_cached(inventory, sku_id, monkeypatch):
    def broken(*_args):
        raise RuntimeError("base caída")

    with monkeypatch.context() as patch:
        patch.setattr(inventory_service, "list_skus", broken)
        assert inventory.get("/inventory/products").status_code == 500
    assert PRODUCTS.stats().entries == 0
    assert inventory.get("/inventory/products").status_code == 200


# --- Lo que no se cachea ----------------------------------------------------------------------------------------


def test_suppliers_list_is_not_cached(seeded_client):
    """Descartado tras medir (CACHING_REPORT.md): un cambio hecho fuera de la API se ve en la petición siguiente."""
    total = len(seeded_client.get("/suppliers").json())
    with suppliers_table() as table:
        table.insert(
            {
                "name": "Proveedor externo",
                "country": "Spain",
                "categories": ["packaging_materials"],
                "rate_per_shipment": 1.25,
                "currency": "EUR",
                "status": "active",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    assert len(seeded_client.get("/suppliers").json()) == total + 1


def test_only_the_two_measured_endpoints_have_a_cache():
    from app.cache import all_caches

    assert set(all_caches()) == {"incidents.summary", "inventory.products"}
