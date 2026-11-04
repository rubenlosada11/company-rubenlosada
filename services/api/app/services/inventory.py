"""Operaciones del inventario (Hito 5): alta de SKUs, movimientos de stock y cálculo del stock.

Reglas de negocio de `CONTEXT-gestor-inventario.es.md`:

1. El stock **siempre se calcula**: `SUMA(StockEntry.quantity) − SUMA(StockExit.quantity)`. No hay columna de stock.
2. Una salida que dejaría el stock por debajo de cero se rechaza **antes de escribir** (`InsufficientStock`).
5. y 6. Los dos almacenes comparten tablas y el stock es **por SKU y por almacén**: los movimientos se filtran por su
   `warehouse` y las cifras de LA y ZGZ nunca se suman.

Las funciones no saben nada de HTTP: lanzan excepciones propias que el router traduce (404, 400, 409). Las usan la API
y el seed (`app/seed_inventory.py`).

`products_cache` guarda el listado de SKUs con su stock (`GET /inventory/products`). Cada escritura que cambia un SKU o
su stock la invalida **después** del commit; una operación rechazada (SKU duplicado, stock insuficiente, SKU que no
existe) no la toca.
"""

import threading
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.cache import TTLCache, register
from app.inventory_models import SKU, StockEntry, StockExit
from app.inventory_schemas import (
    InboundMovement,
    OutboundMovement,
    SKUCreate,
    SKURead,
    SKUSummary,
    StockByWarehouse,
    StockEntryCreate,
    StockExitCreate,
    Warehouse,
)

# Comprobar el stock y registrar la salida es una sola operación: sin el candado, dos salidas simultáneas podrían
# pasar la comprobación con el mismo stock y dejarlo en negativo. Cubre los hilos de un proceso (un solo worker, como
# el resto de la API); en PostgreSQL, además, `with_for_update` bloquea la fila del SKU entre procesos.
_exit_lock = threading.Lock()

# 30 segundos: el stock cambia con cada recepción o salida, pero todas pasan por la API e invalidan la caché al
# momento. El TTL acota el retraso con el que se ven las escrituras de otros procesos (seed, otro worker, cambios
# directos en Supabase). La comprobación de stock de una salida nunca usa la caché (regla 2: `available_stock`), y la
# ficha de un SKU (`GET /inventory/products/{id}`), que consultan los formularios antes de enviar, tampoco.
PRODUCTS_TTL_SECONDS = 30
products_cache = register(TTLCache("inventory.products", PRODUCTS_TTL_SECONDS, list[SKURead]))


class SKUNotFound(Exception):
    def __init__(self, sku_id: int):
        super().__init__(f"No existe ningún SKU con id {sku_id}.")
        self.sku_id = sku_id


class DuplicateSKU(Exception):
    def __init__(self, sku: str):
        super().__init__(f"Ya existe un SKU con el código '{sku}'.")
        self.sku = sku


class InsufficientStock(Exception):
    """Regla 2. Mensaje literal del briefing."""

    def __init__(self, sku: str, available: int, quantity: int):
        super().__init__(f"Insufficient stock for SKU '{sku}'. Available: {available}, requested: {quantity}.")
        self.sku = sku
        self.available = available
        self.quantity = quantity


# --- Cálculo del stock -------------------------------------------------------------------------------------------

StockTable = dict[int, dict[str, int]]


def _sum_by_sku_and_warehouse(
    session: Session, model: type[StockEntry] | type[StockExit], sku_id: int | None
) -> StockTable:
    query = select(model.sku_id, model.warehouse, func.sum(model.quantity)).group_by(model.sku_id, model.warehouse)
    if sku_id is not None:
        query = query.where(model.sku_id == sku_id)
    totals: StockTable = defaultdict(dict)
    for row_sku_id, warehouse, total in session.exec(query):
        totals[row_sku_id][warehouse] = int(total or 0)
    return totals


def stock_by_warehouse(session: Session, sku_id: int | None = None) -> StockTable:
    """`{sku_id: {"LA": n, "ZGZ": m}}` = entradas − salidas de cada almacén. Con `sku_id`, solo ese SKU.

    Dos consultas agregadas (entradas y salidas) para todos los SKUs a la vez: el listado no hace una consulta por SKU.
    """
    entries = _sum_by_sku_and_warehouse(session, StockEntry, sku_id)
    exits = _sum_by_sku_and_warehouse(session, StockExit, sku_id)
    stock: StockTable = {}
    for current in set(entries) | set(exits):
        stock[current] = {
            warehouse.value: entries.get(current, {}).get(warehouse.value, 0)
            - exits.get(current, {}).get(warehouse.value, 0)
            for warehouse in Warehouse
        }
    return stock


def available_stock(session: Session, sku_id: int, warehouse: Warehouse) -> int:
    """Stock de un SKU en un almacén concreto (regla 6)."""
    return stock_by_warehouse(session, sku_id).get(sku_id, {}).get(warehouse.value, 0)


def to_sku_read(sku: SKU, stock: StockTable) -> SKURead:
    by_warehouse = stock.get(sku.id, {}) if sku.id is not None else {}
    breakdown = StockByWarehouse(**{w.value: by_warehouse.get(w.value, 0) for w in Warehouse})
    return SKURead(
        **sku.model_dump(),
        current_stock=getattr(breakdown, sku.warehouse),
        stock_by_warehouse=breakdown,
    )


# --- SKUs ----------------------------------------------------------------------------------------------------------


def list_skus(session: Session, warehouse: Warehouse | None = None) -> list[SKURead]:
    query = select(SKU).order_by(col(SKU.id))
    if warehouse is not None:
        query = query.where(SKU.warehouse == warehouse.value)
    stock = stock_by_warehouse(session)
    return [to_sku_read(sku, stock) for sku in session.exec(query)]


def get_sku(session: Session, sku_id: int) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise SKUNotFound(sku_id)
    return sku


def get_sku_read(session: Session, sku_id: int) -> SKURead:
    return to_sku_read(get_sku(session, sku_id), stock_by_warehouse(session, sku_id))


def find_sku_by_code(session: Session, code: str) -> SKU | None:
    """SKU por su código, sin distinguir mayúsculas (`clt-snk-w-42` es el mismo que `CLT-SNK-W-42`)."""
    return session.exec(select(SKU).where(func.lower(SKU.sku) == code.lower())).first()


def create_sku(session: Session, data: SKUCreate) -> SKURead:
    if find_sku_by_code(session, data.sku) is not None:
        raise DuplicateSKU(data.sku)
    sku = SKU(**data.model_dump(mode="json"))
    session.add(sku)
    try:
        session.commit()
    except IntegrityError:
        # Otra petición ha creado el mismo código entre la comprobación y la escritura (índice único).
        session.rollback()
        raise DuplicateSKU(data.sku) from None
    products_cache.invalidate()
    session.refresh(sku)
    return to_sku_read(sku, {})


# --- Movimientos ---------------------------------------------------------------------------------------------------


def register_entry(session: Session, data: StockEntryCreate, user_uuid: str) -> StockEntry:
    """Recepción de mercancía. Sin almacén, el del SKU."""
    sku = get_sku(session, data.sku_id)
    entry = StockEntry(
        sku_id=sku.id,
        quantity=data.quantity,
        reference=data.reference,
        warehouse=(data.warehouse or Warehouse(sku.warehouse)).value,
        user_uuid=user_uuid,
    )
    session.add(entry)
    session.commit()
    products_cache.invalidate()
    session.refresh(entry)
    return entry


def register_exit(session: Session, data: StockExitCreate, user_uuid: str) -> StockExit:
    """Despacho o pérdida. Rechaza la salida, sin escribir nada, si deja el stock del almacén por debajo de cero."""
    with _exit_lock:
        # `with_for_update`: en PostgreSQL bloquea el SKU hasta el commit (SQLite lo ignora; ahí basta el candado).
        sku = session.exec(select(SKU).where(SKU.id == data.sku_id).with_for_update()).first()
        if sku is None:
            raise SKUNotFound(data.sku_id)
        warehouse = data.warehouse or Warehouse(sku.warehouse)
        available = available_stock(session, sku.id, warehouse)
        if data.quantity > available:
            session.rollback()  # libera el bloqueo de la fila
            raise InsufficientStock(sku.sku, available, data.quantity)

        stock_exit = StockExit(
            sku_id=sku.id,
            quantity=data.quantity,
            exit_type=data.exit_type.value,
            tracking_number=data.tracking_number,
            warehouse=warehouse.value,
            user_uuid=user_uuid,
        )
        session.add(stock_exit)
        session.commit()
        products_cache.invalidate()
    session.refresh(stock_exit)
    return stock_exit


def list_movements(
    session: Session, warehouse: Warehouse | None = None, sku_id: int | None = None
) -> list[InboundMovement | OutboundMovement]:
    """Entradas y salidas juntas, con los datos de su SKU, de la más reciente a la más antigua."""
    entries_query = select(StockEntry, SKU).join(SKU, col(StockEntry.sku_id) == col(SKU.id))
    exits_query = select(StockExit, SKU).join(SKU, col(StockExit.sku_id) == col(SKU.id))
    if warehouse is not None:
        entries_query = entries_query.where(StockEntry.warehouse == warehouse.value)
        exits_query = exits_query.where(StockExit.warehouse == warehouse.value)
    if sku_id is not None:
        entries_query = entries_query.where(StockEntry.sku_id == sku_id)
        exits_query = exits_query.where(StockExit.sku_id == sku_id)

    movements: list[InboundMovement | OutboundMovement] = [
        InboundMovement(**entry.model_dump(), sku=SKUSummary.model_validate(sku))
        for entry, sku in session.exec(entries_query)
    ]
    movements += [
        OutboundMovement(**stock_exit.model_dump(), sku=SKUSummary.model_validate(sku))
        for stock_exit, sku in session.exec(exits_query)
    ]
    # Mismo instante (p. ej. el seed): primero las salidas y, dentro de cada tipo, el id más alto.
    movements.sort(key=lambda m: (m.created_at, m.movement_type == "outbound", m.id), reverse=True)
    return movements
