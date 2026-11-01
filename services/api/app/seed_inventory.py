"""Seed del inventario (Hito 5): `uv run seed-inventory [email]`.

Carga los 6 SKUs de `CONTEXT-gestor-inventario.es.md` y unos movimientos de ejemplo (7 entradas y 4 salidas) en la
base del inventario (`DATABASE_URL` o `services/api/db/inventory.db`).

- **`user_uuid`:** los movimientos se firman con un usuario **existente** de TinyDB (regla 4: no hay usuarios en SQL).
  Por defecto, el primer administrador activo; con `email`, ese usuario. Sin usuarios, el seed no carga nada y explica
  cómo crear uno (`uv run --env-file .env create-admin <email>`).
- **Idempotente:** un SKU se identifica por su código (`sku`) y solo se insertan los que falten. Los movimientos solo
  se cargan si las dos tablas de movimientos están vacías: así nunca se duplican ni se mezclan con los creados desde
  la API.
- Todo pasa por los mismos schemas y funciones que la API: las salidas también se rechazan si dejarían el stock en
  negativo.
"""

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.auth_models import Role, User
from app.database import StorageError, get_database_url, get_engine
from app.inventory_models import StockEntry, StockExit
from app.inventory_schemas import SKUCreate, StockEntryCreate, StockExitCreate
from app.services import inventory as inventory_service
from app.services.users import get_user_by_email, list_users

# Copia literal de la tabla «SKUs» del briefing (un test comprueba que siguen siendo iguales).
SKUS_SEED = [
    {
        "name": "Zapatilla blanca clásica - Talla 42",
        "sku": "CLT-SNK-W-42",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Zapatilla blanca clásica - Talla 42",
        "sku": "CLT-SNK-W-42-Z",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "ZGZ",
    },
    {
        "name": "Auriculares inalámbricos Pro",
        "sku": "TEC-EAR-001",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "LA",
    },
    {
        "name": "Sérum facial hidratante 30ml",
        "sku": "CSM-SRM-030",
        "client_name": "GlowLab Cosmetics",
        "category": "cosmetics",
        "warehouse": "ZGZ",
    },
    {
        "name": "Chino slim fit - marino 32/32",
        "sku": "CLT-CHN-N-32",
        "client_name": "UrbanThread",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Cargador rápido USB-C 65W",
        "sku": "TEC-CHG-065",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "ZGZ",
    },
]

# Recepciones (≥ 4): dos del mismo SKU con cantidades distintas y los dos almacenes. Cada una en el almacén de su SKU.
# Las referencias siguen el formato de ejemplo del briefing («PO-2024-0098», «GR-LA-0234»).
ENTRIES_SEED = [
    {"sku": "CLT-SNK-W-42", "quantity": 40, "reference": "PO-2024-0098", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 25, "reference": "GR-LA-0234", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 30, "reference": "GR-ZGZ-0112", "warehouse": "ZGZ"},
    {"sku": "TEC-EAR-001", "quantity": 60, "reference": "PO-2024-0105", "warehouse": "LA"},
    {"sku": "CSM-SRM-030", "quantity": 120, "reference": "GR-ZGZ-0118", "warehouse": "ZGZ"},
    {"sku": "CLT-CHN-N-32", "quantity": 35, "reference": "PO-2024-0110", "warehouse": "LA"},
    {"sku": "TEC-CHG-065", "quantity": 50, "reference": "GR-ZGZ-0121", "warehouse": "ZGZ"},
]

# Salidas (≥ 3): despachos con número de seguimiento y pérdidas sin él. Ninguna supera lo recibido en su almacén.
EXITS_SEED = [
    {"sku": "CLT-SNK-W-42", "quantity": 12, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456784",
     "warehouse": "LA"},
    {"sku": "TEC-EAR-001", "quantity": 8, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456795",
     "warehouse": "LA"},
    {"sku": "CSM-SRM-030", "quantity": 3, "exit_type": "loss", "tracking_number": None, "warehouse": "ZGZ"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 2, "exit_type": "loss", "tracking_number": None, "warehouse": "ZGZ"},
]


class SeedUserError(Exception):
    """No hay un usuario de TinyDB con el que firmar los movimientos."""


@dataclass
class InventorySeedResult:
    inserted_skus: list[str] = field(default_factory=list)
    skipped_skus: list[str] = field(default_factory=list)
    entries: int = 0
    exits: int = 0
    movements_skipped: bool = False


def resolve_user(email: str | None) -> User:
    """Usuario activo de TinyDB que firma los movimientos: el del email o, sin él, el primer administrador."""
    if email:
        user = get_user_by_email(email.strip().lower())
        if user is None or not user.is_active:
            raise SeedUserError(f"No hay ningún usuario activo con el email {email.strip().lower()}.")
        return user
    admins = sorted(
        (user for user in list_users() if user.role == Role.ADMIN and user.is_active), key=lambda u: u.created_at
    )
    if not admins:
        raise SeedUserError(
            "No hay ningún administrador activo en TinyDB. Crea uno con "
            "`uv run --env-file .env create-admin <email>` o indica el email de un usuario existente."
        )
    return admins[0]


def _count(session: Session, model: type[StockEntry] | type[StockExit]) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def seed_inventory(session: Session, user_uuid: str) -> InventorySeedResult:
    result = InventorySeedResult()
    ids: dict[str, int] = {}

    for raw in SKUS_SEED:
        data = SKUCreate.model_validate(raw)
        existing = inventory_service.find_sku_by_code(session, data.sku)
        if existing is not None:
            ids[data.sku] = existing.id
            result.skipped_skus.append(data.sku)
            continue
        ids[data.sku] = inventory_service.create_sku(session, data).id
        result.inserted_skus.append(data.sku)

    if _count(session, StockEntry) or _count(session, StockExit):
        result.movements_skipped = True
        return result

    for raw in ENTRIES_SEED:
        data = StockEntryCreate.model_validate({**raw, "sku_id": ids[raw["sku"]]})
        inventory_service.register_entry(session, data, user_uuid)
        result.entries += 1
    for raw in EXITS_SEED:
        data = StockExitCreate.model_validate({**raw, "sku_id": ids[raw["sku"]]})
        inventory_service.register_exit(session, data, user_uuid)
        result.exits += 1
    return result


def main() -> int:
    # Si la salida va a una tubería o fichero, Windows usa cp1252 y los acentos se estropean.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="seed-inventory", description="Carga los SKUs y movimientos de ejemplo.")
    parser.add_argument(
        "email", nargs="?", help="Usuario de TinyDB que firma los movimientos (por defecto, el primer admin)"
    )
    args = parser.parse_args()

    try:
        user = resolve_user(args.email)
        with Session(get_engine()) as session:
            result = seed_inventory(session, user.id)
    except SeedUserError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except StorageError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ImportError as error:
        # `DATABASE_URL` de PostgreSQL (Supabase) sin su driver instalado.
        print(
            f"Error: falta el driver de la base de datos ({error.name}). Para PostgreSQL: uv add \"psycopg[binary]\".",
            file=sys.stderr,
        )
        return 1
    except (SQLAlchemyError, OSError) as error:
        # Base no disponible o URL incorrecta. Solo el tipo de error: el mensaje podría llevar la URL con contraseña.
        print(f"Error: no se puede usar la base del inventario ({type(error).__name__}).", file=sys.stderr)
        return 1

    print(f"Base de datos: {_safe_url(get_database_url())}")
    print(f"Usuario de los movimientos: {user.email} ({user.id})")
    for code in result.inserted_skus:
        print(f"  + {code}")
    for code in result.skipped_skus:
        print(f"  = {code} (ya existe)")
    print("Seeder completed.")
    print(f"SKUs inserted: {len(result.inserted_skus)}")
    print(f"SKUs skipped: {len(result.skipped_skus)}")
    if result.movements_skipped:
        print("Movements: skipped (ya hay movimientos en la base)")
    else:
        print(f"Stock entries inserted: {result.entries}")
        print(f"Stock exits inserted: {result.exits}")
    return 0


def _safe_url(url: str) -> str:
    """URL de la base sin la contraseña (la de Supabase la lleva). La de SQLite no tiene: se muestra tal cual."""
    if url.startswith("sqlite"):
        return url
    return make_url(url).render_as_string(hide_password=True)


if __name__ == "__main__":
    sys.exit(main())
