"""Tests del seed del inventario (`uv run seed-inventory`): «Datos Semilla» de CONTEXT-gestor-inventario.es.md."""

import re
from collections import Counter
from pathlib import Path

import pytest
from sqlmodel import Session, func, select

from app.auth_models import Role
from app.database import get_engine
from app.inventory_models import SKU, StockEntry, StockExit
from app.inventory_schemas import SKUCreate
from app.seed_inventory import (
    ENTRIES_SEED,
    EXITS_SEED,
    SKUS_SEED,
    SeedUserError,
    main,
    resolve_user,
    seed_inventory,
)
from app.services import inventory as inventory_service
from app.services.users import update_user

CONTEXT_FILE = Path(__file__).resolve().parents[3] / "CONTEXT-gestor-inventario.es.md"
SKU_COLUMNS = ["name", "sku", "client_name", "category", "warehouse"]


@pytest.fixture(scope="module")
def context_skus():
    """Tabla «SKUs (mínimo 6)» leída directamente del briefing (fuente de verdad)."""
    text = CONTEXT_FILE.read_text(encoding="utf-8")
    section = text.split("### SKUs", 1)[1].split("###", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")]
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    assert header == SKU_COLUMNS
    return [dict(zip(header, (cell.strip() for cell in row.strip("|").split("|")), strict=True)) for row in rows[2:]]


@pytest.fixture
def admin(make_user):
    return make_user("admin@trackflow.test", Role.ADMIN)


def run_seed(user_uuid):
    with Session(get_engine()) as session:
        return seed_inventory(session, user_uuid)


def expected_stock():
    """Stock esperado por código de SKU y almacén, calculado a partir de los datos del seed."""
    stock = Counter()
    for entry in ENTRIES_SEED:
        stock[entry["sku"], entry["warehouse"]] += entry["quantity"]
    for stock_exit in EXITS_SEED:
        stock[stock_exit["sku"], stock_exit["warehouse"]] -= stock_exit["quantity"]
    return stock


# --- Datos ------------------------------------------------------------------------------------------------------------

def test_skus_match_the_briefing_exactly(context_skus):
    assert len(context_skus) == 6
    assert SKUS_SEED == context_skus


def test_seed_data_passes_the_api_schemas():
    for raw in SKUS_SEED:
        SKUCreate.model_validate(raw)


def test_entries_meet_the_briefing_minimums():
    assert len(ENTRIES_SEED) >= 4
    quantities_by_sku = {}
    for entry in ENTRIES_SEED:
        quantities_by_sku.setdefault(entry["sku"], set()).add(entry["quantity"])
    assert any(len(quantities) >= 2 for quantities in quantities_by_sku.values()), "2 recepciones del mismo SKU"
    assert {entry["warehouse"] for entry in ENTRIES_SEED} == {"LA", "ZGZ"}
    assert len({entry["reference"] for entry in ENTRIES_SEED}) == len(ENTRIES_SEED)
    assert {"PO-2024-0098", "GR-LA-0234"} <= {entry["reference"] for entry in ENTRIES_SEED}


def test_exits_meet_the_briefing_minimums():
    assert len(EXITS_SEED) >= 3
    assert any(e["exit_type"] == "dispatch" and e["tracking_number"] == "1Z999AA10123456784" for e in EXITS_SEED)
    assert any(e["exit_type"] == "loss" and e["tracking_number"] is None for e in EXITS_SEED)


def test_movements_use_the_warehouse_of_their_sku_and_never_exceed_the_entries():
    warehouse_by_code = {sku["sku"]: sku["warehouse"] for sku in SKUS_SEED}
    for movement in ENTRIES_SEED + EXITS_SEED:
        assert movement["warehouse"] == warehouse_by_code[movement["sku"]]
    assert all(value >= 0 for value in expected_stock().values())


# --- Carga ------------------------------------------------------------------------------------------------------------

def test_first_run_inserts_skus_and_movements(admin):
    result = run_seed(admin.id)
    assert result.inserted_skus == [sku["sku"] for sku in SKUS_SEED]
    assert (result.skipped_skus, result.entries, result.exits, result.movements_skipped) == (
        [], len(ENTRIES_SEED), len(EXITS_SEED), False
    )
    with Session(get_engine()) as session:
        movements = list(session.exec(select(StockEntry))) + list(session.exec(select(StockExit)))
    assert {movement.user_uuid for movement in movements} == {admin.id}


def test_seeded_stock_is_per_warehouse(admin):
    run_seed(admin.id)
    stock = expected_stock()
    with Session(get_engine()) as session:
        for sku in inventory_service.list_skus(session):
            assert sku.current_stock == stock[sku.sku, sku.warehouse.value]
            assert sku.stock_by_warehouse.LA == stock[sku.sku, "LA"]
            assert sku.stock_by_warehouse.ZGZ == stock[sku.sku, "ZGZ"]
        sneakers = inventory_service.find_sku_by_code(session, "CLT-SNK-W-42")
        assert inventory_service.get_sku_read(session, sneakers.id).current_stock == 40 + 25 - 12


def test_second_run_creates_no_duplicates(admin):
    run_seed(admin.id)
    result = run_seed(admin.id)
    assert result.inserted_skus == []
    assert result.skipped_skus == [sku["sku"] for sku in SKUS_SEED]
    assert result.movements_skipped is True
    with Session(get_engine()) as session:
        assert session.exec(select(func.count()).select_from(SKU)).one() == 6
        assert session.exec(select(func.count()).select_from(StockEntry)).one() == len(ENTRIES_SEED)
        assert session.exec(select(func.count()).select_from(StockExit)).one() == len(EXITS_SEED)


def test_existing_skus_are_kept_and_movements_skipped_if_any_exist(admin):
    with Session(get_engine()) as session:
        existing = inventory_service.create_sku(session, SKUCreate.model_validate({**SKUS_SEED[0], "name": "Propio"}))
        inventory_service.register_entry(
            session,
            inventory_service.StockEntryCreate(sku_id=existing.id, quantity=1, reference="API-1"),
            admin.id,
        )
    result = run_seed(admin.id)
    assert result.skipped_skus == [SKUS_SEED[0]["sku"]]
    assert len(result.inserted_skus) == 5
    assert result.movements_skipped is True
    with Session(get_engine()) as session:
        assert session.get(SKU, existing.id).name == "Propio"
        assert session.exec(select(func.count()).select_from(StockEntry)).one() == 1


# --- Usuario de los movimientos ---------------------------------------------------------------------------------------

def test_resolve_user_without_users_raises():
    with pytest.raises(SeedUserError, match="create-admin"):
        resolve_user(None)


def test_resolve_user_picks_the_first_active_admin(make_user):
    make_user("usuario@trackflow.test")
    first = make_user("primero@trackflow.test", Role.ADMIN)
    make_user("segundo@trackflow.test", Role.ADMIN)
    assert resolve_user(None).id == first.id
    update_user(first.id, {"is_active": False})
    assert resolve_user(None).email == "segundo@trackflow.test"


def test_resolve_user_by_email(make_user):
    user = make_user("operario@trackflow.test")
    assert resolve_user("  Operario@TrackFlow.test ").id == user.id


@pytest.mark.parametrize("email", ["nadie@trackflow.test", "inactivo@trackflow.test"])
def test_resolve_user_rejects_unknown_or_inactive_email(make_user, email):
    inactive = make_user("inactivo@trackflow.test")
    update_user(inactive.id, {"is_active": False})
    with pytest.raises(SeedUserError, match=re.escape(email)):
        resolve_user(email)


# --- CLI --------------------------------------------------------------------------------------------------------------

def test_main_without_users_fails_and_loads_nothing(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["seed-inventory"])
    assert main() == 1
    assert "create-admin" in capsys.readouterr().err
    with Session(get_engine()) as session:
        assert session.exec(select(func.count()).select_from(SKU)).one() == 0


def test_main_prints_real_counts(admin, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["seed-inventory"])
    assert main() == 0
    first = capsys.readouterr().out
    assert main() == 0
    second = capsys.readouterr().out
    assert f"Usuario de los movimientos: {admin.email} ({admin.id})" in first
    assert "SKUs inserted: 6" in first
    assert f"Stock entries inserted: {len(ENTRIES_SEED)}" in first
    assert f"Stock exits inserted: {len(EXITS_SEED)}" in first
    assert "SKUs skipped: 6" in second
    assert "Movements: skipped" in second


def test_main_with_email_argument(make_user, monkeypatch, capsys):
    user = make_user("operario@trackflow.test")
    monkeypatch.setattr("sys.argv", ["seed-inventory", "operario@trackflow.test"])
    assert main() == 0
    assert user.id in capsys.readouterr().out


def test_main_explains_a_missing_postgresql_driver_without_the_password(admin, monkeypatch, capsys):
    # La API instala psycopg; pg8000 no está, así que simula una URL con un driver que falta.
    monkeypatch.setenv("DATABASE_URL", "postgresql+pg8000://postgres:SuperSecreta@127.0.0.1:1/postgres")
    monkeypatch.setattr("sys.argv", ["seed-inventory"])
    assert main() == 1
    output = capsys.readouterr()
    assert "falta el driver de la base de datos (pg8000)" in output.err
    assert "postgresql+psycopg://" in output.err
    assert "SuperSecreta" not in output.err + output.out


def test_main_reports_an_unreachable_postgresql_without_the_password(admin, monkeypatch, capsys):
    # Supabase pausado, host incorrecto o sin red: nada escucha en el puerto 1.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://postgres:SuperSecreta@127.0.0.1:1/postgres")
    monkeypatch.setattr("sys.argv", ["seed-inventory"])
    assert main() == 1
    output = capsys.readouterr()
    assert "no se puede usar la base del inventario (OperationalError)" in output.err
    assert "SuperSecreta" not in output.err + output.out


def test_main_reports_an_unusable_database(admin, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "no-es-una-carpeta"
    blocker.write_text("x")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(blocker / 'inventory.db').as_posix()}")
    monkeypatch.setattr("sys.argv", ["seed-inventory"])
    assert main() == 1
    assert "no se puede usar la base del inventario" in capsys.readouterr().err
