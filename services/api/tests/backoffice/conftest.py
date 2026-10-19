"""Infraestructura de las pruebas unitarias del backoffice: proveedores y gestor de incidencias (API-042, TESTING.md).

Se suma a `tests/conftest.py`, que ya apunta las bases de proveedores (`db_path`) e incidencias
(`incidents_db_path`, autouse) a ficheros temporales. Aquí solo se añade:

- `clock`: congela `app.models.utc_now`, de donde salen `updated_at` y `created_at` de ambos grupos.
- `suppliers`: la tabla real de proveedores, abierta durante el test, para pasarla a las funciones del router.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.database import suppliers_table
from app.incident_models import IncidentCreate
from app.models import SupplierCreate

T0 = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, start: datetime):
        self.now = start

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now


@pytest.fixture
def clock(monkeypatch) -> FrozenClock:
    frozen = FrozenClock(T0)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.now if tz is None else frozen.now.astimezone(tz)

    monkeypatch.setattr("app.models.datetime", FrozenDatetime)
    return frozen


@pytest.fixture
def suppliers(db_path):
    """Tabla `suppliers` del TinyDB temporal. Se mantiene abierta (con su candado) mientras dura el test."""
    with suppliers_table() as table:
        yield table


def supplier_data(**overrides) -> SupplierCreate:
    """Proveedor válido de España (EUR) con un único transportista; `overrides` cambia cualquier campo."""
    data = {
        "name": "MRW España",
        "country": "Spain",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 7.45,
        "currency": "EUR",
        "status": "active",
        **overrides,
    }
    return SupplierCreate(**data)


def incident_data(**overrides) -> IncidentCreate:
    """Incidencia válida (paquete perdido en el almacén de Zaragoza); `overrides` cambia cualquier campo."""
    data = {
        "title": "Paquete perdido",
        "description": "El cliente no ha recibido el envío.",
        "category": "lost_parcel",
        "origin": "customer",
        "branch": "zaragoza_warehouse",
        **overrides,
    }
    return IncidentCreate(**data)
