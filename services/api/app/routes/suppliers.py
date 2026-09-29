"""Endpoints del directorio de proveedores (`/suppliers`).

Todos requieren un usuario autenticado (Bearer JWT): tarifas negociadas y contactos son datos comerciales internos.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from tinydb.table import Document, Table

from app.database import get_suppliers_table
from app.dependencies import get_current_user
from app.models import (
    Category,
    Country,
    Supplier,
    SupplierCreate,
    SupplierRateUpdate,
    SupplierStatusUpdate,
    utc_now,
)

router = APIRouter(
    prefix="/suppliers",
    tags=["suppliers"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"description": "Sin token o con un token no válido o caducado"}},
)

SuppliersTable = Annotated[Table, Depends(get_suppliers_table)]

NOT_FOUND = {404: {"description": "Proveedor no encontrado"}}


def to_supplier(doc: Document) -> Supplier:
    """Documento de TinyDB → modelo de respuesta (el `id` es el `doc_id` de TinyDB)."""
    return Supplier.model_validate({**doc, "id": doc.doc_id})


def get_or_404(table: Table, supplier_id: int) -> Document:
    doc = table.get(doc_id=supplier_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Proveedor {supplier_id} no encontrado")
    return doc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, table: SuppliersTable) -> Supplier:
    doc_id = table.insert({**payload.model_dump(mode="json"), "updated_at": utc_now().isoformat()})
    return to_supplier(table.get(doc_id=doc_id))


@router.get("")
def list_suppliers(
    table: SuppliersTable,
    country: Country | None = None,
    category: Category | None = None,
) -> list[Supplier]:
    """Todos los proveedores; `country` y `category` son filtros opcionales y combinables (AND).

    `category` devuelve los proveedores que tienen esa categoría entre sus `categories`.
    """
    docs = table.all()
    if country is not None:
        docs = [doc for doc in docs if doc["country"] == country]
    if category is not None:
        docs = [doc for doc in docs if category in doc["categories"]]
    return [to_supplier(doc) for doc in docs]


@router.get("/{supplier_id}", responses=NOT_FOUND)
def get_supplier(supplier_id: int, table: SuppliersTable) -> Supplier:
    return to_supplier(get_or_404(table, supplier_id))


@router.patch("/{supplier_id}/rate", responses=NOT_FOUND)
def update_rate(supplier_id: int, payload: SupplierRateUpdate, table: SuppliersTable) -> Supplier:
    """Actualiza la tarifa y registra `updated_at` (trazabilidad de tarifas del CONTEXT)."""
    get_or_404(table, supplier_id)
    table.update(
        {"rate_per_shipment": payload.rate_per_shipment, "updated_at": utc_now().isoformat()},
        doc_ids=[supplier_id],
    )
    return to_supplier(table.get(doc_id=supplier_id))


@router.patch("/{supplier_id}/status", responses=NOT_FOUND)
def update_status(supplier_id: int, payload: SupplierStatusUpdate, table: SuppliersTable) -> Supplier:
    """Activa o suspende. No toca `updated_at`, que es la fecha de la última actualización de tarifa."""
    get_or_404(table, supplier_id)
    table.update({"status": payload.status.value}, doc_ids=[supplier_id])
    return to_supplier(table.get(doc_id=supplier_id))


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_supplier(supplier_id: int, table: SuppliersTable) -> None:
    get_or_404(table, supplier_id)
    table.remove(doc_ids=[supplier_id])
