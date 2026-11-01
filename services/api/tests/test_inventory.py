"""Tests HTTP del inventario (`/inventory`, Hito 5). Contexto: CONTEXT-gestor-inventario.es.md.

Incluyen las comprobaciones de las «Notas de evaluación» del briefing: salida que supera el stock del almacén → 400,
`dispatch` sin `tracking_number` → error de validación, stock por almacén (no agregado) y `warehouse` presente en los
tres modelos y sus respuestas.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.database import get_engine
from app.inventory_models import StockEntry, StockExit
from app.inventory_schemas import ExitType, StockEntryCreate, StockExitCreate, Warehouse
from app.main import app
from app.services import inventory as inventory_service
from tests.conftest import bearer

SNEAKER = {
    "name": "Zapatilla blanca clásica - Talla 42",
    "sku": "CLT-SNK-W-42",
    "client_name": "PureStep Footwear",
    "category": "fashion",
    "warehouse": "LA",
}
TRACKING = "1Z999AA10123456784"


@pytest.fixture
def operator(make_user):
    return make_user("operario@trackflow.test")


@pytest.fixture
def api(operator):
    """Cliente autenticado como un usuario de TinyDB (su UUID debe acabar en `user_uuid`)."""
    return TestClient(app, headers=bearer(operator))


def create_sku(api, **overrides):
    response = api.post("/inventory/products", json={**SNEAKER, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def inbound(api, sku_id, quantity, **extra):
    return api.post(
        "/inventory/orders/inbound", json={"sku_id": sku_id, "quantity": quantity, "reference": "PO-2024-0098", **extra}
    )


def outbound(api, sku_id, quantity, exit_type="dispatch", **extra):
    body = {"sku_id": sku_id, "quantity": quantity, "exit_type": exit_type, **extra}
    if exit_type == "dispatch" and "tracking_number" not in extra:
        body["tracking_number"] = TRACKING
    return api.post("/inventory/orders/outbound", json=body)


def movement_counts():
    with Session(get_engine()) as session:
        entries = session.exec(select(func.count()).select_from(StockEntry)).one()
        exits = session.exec(select(func.count()).select_from(StockExit)).one()
    return entries, exits


# --- Autenticación ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/inventory/products"),
        ("post", "/inventory/products"),
        ("get", "/inventory/products/1"),
        ("post", "/inventory/orders/inbound"),
        ("post", "/inventory/orders/outbound"),
        ("get", "/inventory/orders"),
    ],
)
def test_every_route_requires_a_token(method, path):
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_routes_are_registered_under_inventory_prefix():
    paths = {path for path in app.openapi()["paths"] if path.startswith("/inventory")}
    assert paths == {
        "/inventory/products",
        "/inventory/products/{sku_id}",
        "/inventory/orders/inbound",
        "/inventory/orders/outbound",
        "/inventory/orders",
    }


# --- SKUs ------------------------------------------------------------------------------------------------------------

def test_create_sku_returns_201_with_calculated_stock(api):
    response = api.post("/inventory/products", json=SNEAKER)
    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        **SNEAKER,
        "current_stock": 0,
        "stock_by_warehouse": {"LA": 0, "ZGZ": 0},
    }


def test_create_sku_ignores_server_fields_sent_by_the_client(api):
    body = create_sku(api, id=99, current_stock=500, stock_by_warehouse={"LA": 500, "ZGZ": 0})
    assert body["id"] == 1
    assert body["current_stock"] == 0
    assert body["stock_by_warehouse"] == {"LA": 0, "ZGZ": 0}


def test_create_sku_trims_whitespace(api):
    body = create_sku(api, name="  Zapatilla  ", sku=" CLT-1 ", client_name=" PureStep ")
    assert (body["name"], body["sku"], body["client_name"]) == ("Zapatilla", "CLT-1", "PureStep")


@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "food"},
        {"category": "Fashion"},
        {"warehouse": "MAD"},
        {"warehouse": "la"},
        {"name": ""},
        {"name": "   "},
        {"sku": ""},
        {"client_name": ""},
        {"sku": "X" * 65},
        {"name": 42},
    ],
)
def test_create_sku_rejects_invalid_values(api, overrides):
    response = api.post("/inventory/products", json={**SNEAKER, **overrides})
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]


@pytest.mark.parametrize("missing", ["name", "sku", "client_name", "category", "warehouse"])
def test_create_sku_requires_every_field(api, missing):
    body = {key: value for key, value in SNEAKER.items() if key != missing}
    response = api.post("/inventory/products", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]


@pytest.mark.parametrize("code", ["CLT-SNK-W-42", "clt-snk-w-42", "  CLT-SNK-W-42 "])
def test_duplicate_sku_code_returns_409(api, code):
    create_sku(api)
    response = api.post("/inventory/products", json={**SNEAKER, "sku": code, "warehouse": "ZGZ"})
    assert response.status_code == 409
    assert response.json() == {"detail": f"Ya existe un SKU con el código '{code.strip()}'."}
    assert len(api.get("/inventory/products").json()) == 1


def test_list_products_in_id_order_with_stock(api):
    first = create_sku(api)
    second = create_sku(api, sku="TEC-EAR-001", name="Auriculares", category="electronics")
    inbound(api, first["id"], 10)
    response = api.get("/inventory/products")
    assert response.status_code == 200
    body = response.json()
    assert [sku["id"] for sku in body] == [first["id"], second["id"]]
    assert [sku["current_stock"] for sku in body] == [10, 0]


def test_list_products_empty(api):
    assert api.get("/inventory/products").json() == []


def test_list_products_filters_by_warehouse(api):
    create_sku(api)
    zgz = create_sku(api, sku="CLT-SNK-W-42-Z", warehouse="ZGZ")
    body = api.get("/inventory/products", params={"warehouse": "ZGZ"}).json()
    assert [sku["id"] for sku in body] == [zgz["id"]]


def test_list_products_rejects_unknown_warehouse(api):
    assert api.get("/inventory/products", params={"warehouse": "MAD"}).status_code == 422


def test_get_product_with_current_stock(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 40)
    inbound(api, sku["id"], 25)
    outbound(api, sku["id"], 12)
    response = api.get(f"/inventory/products/{sku['id']}")
    assert response.status_code == 200
    assert response.json() == {**sku, "current_stock": 53, "stock_by_warehouse": {"LA": 53, "ZGZ": 0}}


def test_get_unknown_product_returns_404(api):
    response = api.get("/inventory/products/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "No existe ningún SKU con id 999."}


def test_get_product_with_non_integer_id_returns_422(api):
    assert api.get("/inventory/products/abc").status_code == 422


# --- Entradas (StockEntry) -------------------------------------------------------------------------------------------

def test_inbound_returns_201_with_server_fields(api, operator):
    sku = create_sku(api)
    before = datetime.now(UTC)
    response = inbound(api, sku["id"], 40, warehouse="LA")
    assert response.status_code == 201
    body = response.json()
    assert list(body) == ["id", "sku_id", "quantity", "reference", "warehouse", "created_at", "user_uuid"]
    assert body["id"] == 1
    assert (body["sku_id"], body["quantity"], body["reference"], body["warehouse"]) == (
        sku["id"], 40, "PO-2024-0098", "LA"
    )
    assert body["user_uuid"] == operator.id
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= created_at <= datetime.now(UTC) + timedelta(seconds=1)


def test_inbound_ignores_user_uuid_and_created_at_from_the_body(api, operator):
    sku = create_sku(api)
    body = inbound(api, sku["id"], 5, user_uuid="otro-usuario", created_at="2020-01-01T00:00:00Z").json()
    assert body["user_uuid"] == operator.id
    assert not body["created_at"].startswith("2020")


def test_inbound_defaults_to_the_sku_warehouse(api):
    sku = create_sku(api, warehouse="ZGZ", sku="CLT-SNK-W-42-Z")
    assert inbound(api, sku["id"], 5).json()["warehouse"] == "ZGZ"


@pytest.mark.parametrize("quantity", [0, -1, "5", 5.5, 5.0, True, None, 2_147_483_648])
def test_inbound_rejects_invalid_quantity(api, quantity):
    sku = create_sku(api)
    response = inbound(api, sku["id"], quantity)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "quantity"]
    assert movement_counts() == (0, 0)


@pytest.mark.parametrize("extra", [{"reference": ""}, {"reference": "   "}, {"warehouse": "MAD"}])
def test_inbound_rejects_invalid_reference_or_warehouse(api, extra):
    sku = create_sku(api)
    assert inbound(api, sku["id"], 5, **extra).status_code == 422


def test_inbound_requires_reference(api):
    sku = create_sku(api)
    response = api.post("/inventory/orders/inbound", json={"sku_id": sku["id"], "quantity": 5})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "reference"]


def test_inbound_for_unknown_sku_returns_404_and_writes_nothing(api):
    response = inbound(api, 999, 5)
    assert response.status_code == 404
    assert response.json() == {"detail": "No existe ningún SKU con id 999."}
    assert movement_counts() == (0, 0)


def test_two_entries_of_the_same_sku_add_up(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 40)
    inbound(api, sku["id"], 25, reference="GR-LA-0234")
    assert api.get(f"/inventory/products/{sku['id']}").json()["current_stock"] == 65


# --- Salidas (StockExit) ---------------------------------------------------------------------------------------------

def test_dispatch_returns_201(api, operator):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 12)
    assert response.status_code == 201
    body = response.json()
    assert list(body) == [
        "id", "sku_id", "quantity", "exit_type", "tracking_number", "warehouse", "created_at", "user_uuid"
    ]
    assert (body["exit_type"], body["tracking_number"], body["warehouse"], body["quantity"]) == (
        "dispatch", TRACKING, "LA", 12
    )
    assert body["user_uuid"] == operator.id
    assert api.get(f"/inventory/products/{sku['id']}").json()["current_stock"] == 8


def test_loss_without_tracking_number_returns_201(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 3, exit_type="loss")
    assert response.status_code == 201
    assert response.json()["tracking_number"] is None
    assert response.json()["exit_type"] == "loss"


def test_loss_with_blank_tracking_number_is_stored_as_null(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 3, exit_type="loss", tracking_number="  ")
    assert response.status_code == 201
    assert response.json()["tracking_number"] is None


@pytest.mark.parametrize("tracking", [None, "", "   "])
def test_dispatch_without_tracking_number_is_a_validation_error(api, tracking):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 5, tracking_number=tracking)
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "tracking_number"]
    assert "tracking_number es obligatorio cuando exit_type es 'dispatch'" in error["msg"]
    assert movement_counts() == (1, 0)


def test_dispatch_with_tracking_number_omitted_is_a_validation_error(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = api.post(
        "/inventory/orders/outbound", json={"sku_id": sku["id"], "quantity": 5, "exit_type": "dispatch"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "tracking_number"]


def test_loss_with_tracking_number_is_a_validation_error(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 5, exit_type="loss", tracking_number=TRACKING)
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "tracking_number"]
    assert "tracking_number debe ser nulo cuando exit_type es 'loss'" in error["msg"]
    assert movement_counts() == (1, 0)


@pytest.mark.parametrize("exit_type", ["return", "DISPATCH", "", None])
def test_outbound_rejects_unknown_exit_type(api, exit_type):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = api.post(
        "/inventory/orders/outbound",
        json={"sku_id": sku["id"], "quantity": 5, "exit_type": exit_type, "tracking_number": TRACKING},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "exit_type"]


@pytest.mark.parametrize("quantity", [0, -3, "2", 1.5, False])
def test_outbound_rejects_invalid_quantity(api, quantity):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    assert outbound(api, sku["id"], quantity).status_code == 422


def test_outbound_for_unknown_sku_returns_404(api):
    response = outbound(api, 999, 1)
    assert response.status_code == 404
    assert response.json() == {"detail": "No existe ningún SKU con id 999."}


def test_exit_above_stock_returns_400_with_the_exact_message_and_writes_nothing(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    response = outbound(api, sku["id"], 25)
    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient stock for SKU 'CLT-SNK-W-42'. Available: 20, requested: 25."}
    assert movement_counts() == (1, 0)
    assert api.get(f"/inventory/products/{sku['id']}").json()["current_stock"] == 20


def test_exit_without_any_stock_returns_400(api):
    sku = create_sku(api)
    response = outbound(api, sku["id"], 1, exit_type="loss")
    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient stock for SKU 'CLT-SNK-W-42'. Available: 0, requested: 1."}


def test_exit_can_take_the_stock_exactly_to_zero_but_not_below(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    assert outbound(api, sku["id"], 20).status_code == 201
    assert api.get(f"/inventory/products/{sku['id']}").json()["current_stock"] == 0
    response = outbound(api, sku["id"], 1, exit_type="loss")
    assert response.status_code == 400
    assert response.json()["detail"].endswith("Available: 0, requested: 1.")


def test_previous_exits_count_against_the_stock(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    outbound(api, sku["id"], 12)
    response = outbound(api, sku["id"], 9, exit_type="loss")
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock for SKU 'CLT-SNK-W-42'. Available: 8, requested: 9."


def test_concurrent_exits_never_take_stock_below_zero(api, operator):
    """Regla 2 con peticiones simultáneas: 10 salidas de 3 unidades sobre 20 → exactamente 6 aceptadas."""
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    start = threading.Barrier(10)
    results: list[str] = []

    def worker():
        start.wait()
        with Session(get_engine()) as session:
            try:
                inventory_service.register_exit(
                    session, StockExitCreate(sku_id=sku["id"], quantity=3, exit_type=ExitType.LOSS), operator.id
                )
                results.append("ok")
            except inventory_service.InsufficientStock:
                results.append("rejected")

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("ok") == 6
    assert results.count("rejected") == 4
    assert api.get(f"/inventory/products/{sku['id']}").json()["current_stock"] == 2


# --- Regla 6: stock por SKU y por almacén ----------------------------------------------------------------------------

def test_stock_is_per_warehouse_not_aggregated(api):
    """Ejemplo del briefing: 20 unidades en LA y 15 en ZGZ son dos cifras separadas, no 35."""
    sku = create_sku(api)  # registrado en LA
    inbound(api, sku["id"], 20, warehouse="LA")
    inbound(api, sku["id"], 15, warehouse="ZGZ")

    body = api.get(f"/inventory/products/{sku['id']}").json()
    assert body["current_stock"] == 20
    assert body["stock_by_warehouse"] == {"LA": 20, "ZGZ": 15}
    listed = api.get("/inventory/products").json()[0]
    assert listed["current_stock"] == 20
    assert listed["stock_by_warehouse"] == {"LA": 20, "ZGZ": 15}


def test_exit_is_checked_against_the_stock_of_its_own_warehouse(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20, warehouse="LA")
    inbound(api, sku["id"], 15, warehouse="ZGZ")

    rejected = outbound(api, sku["id"], 16, warehouse="ZGZ")
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "Insufficient stock for SKU 'CLT-SNK-W-42'. Available: 15, requested: 16."

    accepted = outbound(api, sku["id"], 16, warehouse="LA")
    assert accepted.status_code == 201
    assert accepted.json()["warehouse"] == "LA"
    assert api.get(f"/inventory/products/{sku['id']}").json()["stock_by_warehouse"] == {"LA": 4, "ZGZ": 15}


def test_exit_without_warehouse_uses_the_sku_warehouse(api):
    sku = create_sku(api, warehouse="ZGZ", sku="CLT-SNK-W-42-Z")
    inbound(api, sku["id"], 10, warehouse="LA")  # stock en LA, no en ZGZ
    response = outbound(api, sku["id"], 1)
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock for SKU 'CLT-SNK-W-42-Z'. Available: 0, requested: 1."


def test_the_same_product_in_two_warehouses_keeps_two_stock_figures(api):
    la = create_sku(api)
    zgz = create_sku(api, sku="CLT-SNK-W-42-Z", warehouse="ZGZ")
    inbound(api, la["id"], 20)
    inbound(api, zgz["id"], 15)
    stocks = {sku["sku"]: sku["current_stock"] for sku in api.get("/inventory/products").json()}
    assert stocks == {"CLT-SNK-W-42": 20, "CLT-SNK-W-42-Z": 15}


def test_warehouse_is_present_in_every_response(api):
    sku = create_sku(api)
    entry = inbound(api, sku["id"], 5).json()
    stock_exit = outbound(api, sku["id"], 1).json()
    assert sku["warehouse"] == entry["warehouse"] == stock_exit["warehouse"] == "LA"
    for movement in api.get("/inventory/orders").json():
        assert movement["warehouse"] == "LA"
        assert movement["sku"]["warehouse"] == "LA"


# --- Movimientos (GET /inventory/orders) -----------------------------------------------------------------------------

def test_list_orders_returns_both_movement_types_with_sku_data(api, operator):
    sku = create_sku(api)
    entry = inbound(api, sku["id"], 20).json()
    stock_exit = outbound(api, sku["id"], 4).json()
    response = api.get("/inventory/orders")
    assert response.status_code == 200
    summary = {key: sku[key] for key in ("id", "name", "sku", "client_name", "category", "warehouse")}
    assert response.json() == [
        {**stock_exit, "movement_type": "outbound", "sku": summary},
        {**entry, "movement_type": "inbound", "sku": summary},
    ]


def test_list_orders_is_newest_first(api):
    sku = create_sku(api)
    inbound(api, sku["id"], 20)
    outbound(api, sku["id"], 1)
    inbound(api, sku["id"], 5, reference="GR-LA-0234")
    body = api.get("/inventory/orders").json()
    assert [(m["movement_type"], m["id"]) for m in body] == [("inbound", 2), ("outbound", 1), ("inbound", 1)]
    stamps = [datetime.fromisoformat(m["created_at"]) for m in body]
    assert stamps == sorted(stamps, reverse=True)


def test_list_orders_empty(api):
    assert api.get("/inventory/orders").json() == []


def test_list_orders_filters_by_warehouse_and_sku(api):
    first = create_sku(api)
    second = create_sku(api, sku="TEC-EAR-001", name="Auriculares", category="electronics")
    inbound(api, first["id"], 20, warehouse="LA")
    inbound(api, first["id"], 7, warehouse="ZGZ")
    inbound(api, second["id"], 9, warehouse="LA")

    zgz = api.get("/inventory/orders", params={"warehouse": "ZGZ"}).json()
    assert [(m["sku_id"], m["quantity"]) for m in zgz] == [(first["id"], 7)]
    only_second = api.get("/inventory/orders", params={"sku_id": second["id"]}).json()
    assert [(m["sku_id"], m["quantity"]) for m in only_second] == [(second["id"], 9)]
    both = api.get("/inventory/orders", params={"warehouse": "LA", "sku_id": first["id"]}).json()
    assert [(m["sku_id"], m["quantity"]) for m in both] == [(first["id"], 20)]


@pytest.mark.parametrize("params", [{"warehouse": "MAD"}, {"sku_id": 0}, {"sku_id": "abc"}])
def test_list_orders_rejects_invalid_filters(api, params):
    assert api.get("/inventory/orders", params=params).status_code == 422


# --- Servicio --------------------------------------------------------------------------------------------------------

def test_stock_is_never_stored_as_a_column():
    """Regla 1: `current_stock` no existe en la tabla de SKUs; se calcula siempre."""
    from app.inventory_models import SKU

    assert "current_stock" not in SKU.__table__.columns
    assert "stock_by_warehouse" not in SKU.__table__.columns


def test_service_stock_table_for_all_skus(api, operator):
    first = create_sku(api)
    second = create_sku(api, sku="CSM-SRM-030", name="Sérum", category="cosmetics", warehouse="ZGZ")
    with Session(get_engine()) as session:
        inventory_service.register_entry(
            session,
            StockEntryCreate(sku_id=first["id"], quantity=10, reference="A", warehouse=Warehouse.ZGZ),
            operator.id,
        )
        inventory_service.register_entry(
            session, StockEntryCreate(sku_id=second["id"], quantity=4, reference="B"), operator.id
        )
        assert inventory_service.stock_by_warehouse(session) == {
            first["id"]: {"LA": 0, "ZGZ": 10},
            second["id"]: {"LA": 0, "ZGZ": 4},
        }
        assert inventory_service.available_stock(session, first["id"], Warehouse.LA) == 0
        assert inventory_service.available_stock(session, 999, Warehouse.LA) == 0


def test_duplicate_created_between_check_and_write_is_still_a_409(api, monkeypatch):
    """Dos altas simultáneas del mismo código: la comprobación previa no lo ve, el índice único sí."""
    create_sku(api)
    monkeypatch.setattr(inventory_service, "find_sku_by_code", lambda session, code: None)
    response = api.post("/inventory/products", json={**SNEAKER, "warehouse": "ZGZ"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un SKU con el código 'CLT-SNK-W-42'."}
    assert len(api.get("/inventory/products").json()) == 1


def test_unavailable_database_is_a_generic_500_without_the_url(api, monkeypatch):
    """`DATABASE_URL` de PostgreSQL sin driver (o base caída): solo falla el inventario, sin filtrar la contraseña."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:SuperSecreta@127.0.0.1:1/postgres")
    response = TestClient(app, headers=api.headers, raise_server_exceptions=False).get("/inventory/products")
    assert response.status_code == 500
    assert response.json() == {"detail": "Error interno del servidor."}
    assert "SuperSecreta" not in response.text
    assert TestClient(app).get("/health").status_code == 200
