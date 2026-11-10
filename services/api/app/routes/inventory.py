"""Endpoints del inventario unificado de los almacenes de Los Ángeles y Zaragoza (Hito 5, ticket TRK-0341).

Contexto: `CONTEXT-gestor-inventario.es.md`. Todas las rutas cuelgan de `/inventory` y requieren un usuario autenticado
(Bearer JWT de TinyDB): el `user_uuid` de cada movimiento es el del usuario del token, nunca un dato del cuerpo.

Errores: 401 sin token; 404 si el SKU no existe; 409 si el código de SKU ya existe; 400 si una salida deja el stock por
debajo de cero (mensaje literal del briefing); 422 si los datos no son válidos (p. ej. un `dispatch` sin
`tracking_number`).

Telemetría: los rechazos de órdenes (`inventory_order_rejected`) se emiten aquí, en los `except`; las órdenes
registradas, en el servicio. `create_product` detecta además el caso 3 de `direct_stock_edit_rejected`: un alta que
intenta fijar el stock (`current_stock`, `stock` o `stock_by_warehouse` en el cuerpo), que la API ignora.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session

from app.auth_models import User
from app.database import get_database_url, get_db
from app.dependencies import CurrentUser, get_current_user
from app.inventory_schemas import (
    Movement,
    SKUCreate,
    SKURead,
    StockEntryCreate,
    StockEntryRead,
    StockExitCreate,
    StockExitRead,
    Warehouse,
)
from app.services import inventory as inventory_service
from app.telemetry import emitter as telemetry
from app.telemetry.context import STOCK_FIELDS, stock_value

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"description": "Sin token o con un token no válido o caducado"}},
)

DbSession = Annotated[Session, Depends(get_db)]

SKU_NOT_FOUND = {404: {"description": "SKU no encontrado"}}


def not_found(error: inventory_service.SKUNotFound) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error))


async def report_stock_fields(request: Request) -> None:
    """Caso 3 de `direct_stock_edit_rejected`: el cuerpo del alta trae campos de stock (la API no los aplica).

    Lee el cuerpo ya recibido (FastAPI lo guarda), así que se emite aunque el alta acabe en 409 o 422: cada intento
    cuenta. No cambia la respuesta (rechazarlo con 422 es un cambio funcional pendiente de aprobar, plan §17.3).
    """
    try:
        body = await request.json()
    except ValueError:
        return
    if not isinstance(body, dict) or not any(name in body for name in STOCK_FIELDS):
        return
    await run_in_threadpool(
        telemetry.emit_direct_stock_edit_rejected,
        channel="stock_field_in_payload",
        route_template="/inventory/products",
        http_method="POST",
        quantity=stock_value(body),
        product=telemetry.product_from_payload(body),
    )


@router.get("/products", response_model=list[SKURead], summary="Lista los SKUs con su stock")
def list_products(
    session: DbSession,
    warehouse: Annotated[Warehouse | None, Query(description="Solo los SKUs registrados en este almacén")] = None,
) -> list[SKURead]:
    """`current_stock` es el stock en el almacén del SKU; `stock_by_warehouse`, el de cada almacén por separado.

    Se sirve desde una caché de 30 s que se invalida con cada alta de SKU, entrada o salida (`products_cache`).
    """
    key = (get_database_url(), warehouse)
    return inventory_service.products_cache.get_or_load(key, lambda: inventory_service.list_skus(session, warehouse))


@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    response_model=SKURead,
    summary="Registra un SKU",
    responses={409: {"description": "Ya existe un SKU con ese código"}},
    dependencies=[Depends(report_stock_fields)],
)
def create_product(payload: SKUCreate, session: DbSession) -> SKURead:
    try:
        return inventory_service.create_sku(session, payload)
    except inventory_service.DuplicateSKU as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None


@router.get(
    "/products/{sku_id}", response_model=SKURead, summary="Obtiene un SKU con su stock", responses=SKU_NOT_FOUND
)
def get_product(sku_id: int, session: DbSession) -> SKURead:
    try:
        return inventory_service.get_sku_read(session, sku_id)
    except inventory_service.SKUNotFound as error:
        raise not_found(error) from None


@router.post(
    "/orders/inbound",
    status_code=status.HTTP_201_CREATED,
    response_model=StockEntryRead,
    summary="Registra una recepción de mercancía (StockEntry)",
    responses=SKU_NOT_FOUND,
)
def create_inbound(payload: StockEntryCreate, session: DbSession, user: CurrentUser) -> StockEntryRead:
    try:
        entry = inventory_service.register_entry(session, payload, _user_uuid(user))
    except inventory_service.SKUNotFound as error:
        telemetry.emit_order_rejected(
            order_type="inbound",
            reason="sku_not_found",
            quantity=payload.quantity,
            actor_id=_user_uuid(user),
            warehouse_code=payload.warehouse.value if payload.warehouse else None,
        )
        raise not_found(error) from None
    return StockEntryRead.model_validate(entry)


@router.post(
    "/orders/outbound",
    status_code=status.HTTP_201_CREATED,
    response_model=StockExitRead,
    summary="Registra un despacho o una pérdida (StockExit)",
    responses={**SKU_NOT_FOUND, 400: {"description": "Stock insuficiente en el almacén de la salida"}},
)
def create_outbound(payload: StockExitCreate, session: DbSession, user: CurrentUser) -> StockExitRead:
    try:
        stock_exit = inventory_service.register_exit(session, payload, _user_uuid(user))
    except inventory_service.SKUNotFound as error:
        telemetry.emit_order_rejected(
            order_type="outbound",
            reason="sku_not_found",
            quantity=payload.quantity,
            actor_id=_user_uuid(user),
            warehouse_code=payload.warehouse.value if payload.warehouse else None,
            exit_type=payload.exit_type.value,
        )
        raise not_found(error) from None
    except inventory_service.InsufficientStock as error:
        telemetry.emit_order_rejected(
            order_type="outbound",
            reason="insufficient_stock",
            quantity=payload.quantity,
            actor_id=_user_uuid(user),
            sku=inventory_service.get_sku(session, payload.sku_id),
            warehouse_code=payload.warehouse.value if payload.warehouse else None,
            available=error.available,
            exit_type=payload.exit_type.value,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    return StockExitRead.model_validate(stock_exit)


@router.get("/orders", response_model=list[Movement], summary="Lista los movimientos de stock con los datos del SKU")
def list_orders(
    session: DbSession,
    warehouse: Annotated[Warehouse | None, Query(description="Solo los movimientos de este almacén")] = None,
    sku_id: Annotated[int | None, Query(gt=0, description="Solo los movimientos de este SKU")] = None,
) -> list[Movement]:
    """Entradas (`movement_type: "inbound"`) y salidas (`"outbound"`), de la más reciente a la más antigua."""
    return inventory_service.list_movements(session, warehouse, sku_id)


def _user_uuid(user: User) -> str:
    """Regla 4: el usuario vive en TinyDB; en SQL solo se guarda su UUID (el `sub` del JWT)."""
    return user.id
