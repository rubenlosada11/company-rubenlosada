"""Dataset sintético y reproducible para medir la caché de la API (`CACHING_REPORT.md`).

Crea, en un directorio **nuevo**, las cuatro bases que usa `services/api`:

    suppliers.json   proveedores           (TinyDB)
    incidents.json   gestor de incidencias (TinyDB)
    auth.json        un usuario de benchmark (TinyDB)
    inventory.db     SKUs, entradas y salidas (SQLite con las tablas SQLModel de la API)

Nunca escribe en `services/api/db/` ni en la base de `DATABASE_URL`: se niega si el directorio de salida ya existe o
está dentro de `services/api/db`. No sirve para producción: los datos son ficticios ("Bench …") y deterministas
(misma `--seed`, mismos datos).

Uso (desde la raíz del repo; la contraseña del usuario de benchmark la elige quien lo ejecuta):

    uv run --project services/api python audit/caching/seed_benchmark.py <directorio> --password <contraseña>
"""

import argparse
import os
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DB_DIR = (REPO_ROOT / "services" / "api" / "db").resolve()

# Volumen por defecto: decenas de veces el de las bases locales (15 proveedores, 95 incidencias, 6 SKUs, 15
# movimientos), para que el coste de leer y agregar se vea en las mediciones.
DEFAULTS = {"suppliers": 500, "incidents": 5000, "skus": 1000, "entries": 20000, "exits": 15000}
BENCH_EMAIL = "benchmark@trackflow.test"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, help="Directorio nuevo donde se crean las bases")
    parser.add_argument("--password", required=True, help="Contraseña del usuario de benchmark (≥ 8 caracteres)")
    parser.add_argument("--seed", type=int, default=20261102, help="Semilla del generador (reproducible)")
    for name, value in DEFAULTS.items():
        parser.add_argument(f"--{name}", type=int, default=value, help=f"Número de {name} (por defecto {value})")
    return parser.parse_args()


def safe_out_dir(out: Path) -> Path:
    out = out.resolve()
    if out == REAL_DB_DIR or REAL_DB_DIR in out.parents:
        sys.exit(f"Me niego a escribir en {out}: es el directorio de las bases reales de la API.")
    if out.exists():
        sys.exit(f"{out} ya existe: el dataset se crea siempre en un directorio nuevo.")
    out.mkdir(parents=True)
    return out


def point_env_to(out: Path) -> None:
    """Antes de importar la API: todas sus bases apuntan al directorio de benchmark."""
    os.environ["SUPPLIERS_DB_PATH"] = str(out / "suppliers.json")
    os.environ["INCIDENTS_DB_PATH"] = str(out / "incidents.json")
    os.environ["AUTH_DB_PATH"] = str(out / "auth.json")
    os.environ["DATABASE_URL"] = f"sqlite:///{(out / 'inventory.db').as_posix()}"


def seed_suppliers(rng: random.Random, count: int, now: datetime) -> None:
    from app.database import suppliers_table
    from app.models import CURRENCY_BY_COUNTRY, Category, Country, Status, SupplierCreate

    categories = list(Category)
    docs = []
    for number in range(1, count + 1):
        country = rng.choice(list(Country))
        supplier = SupplierCreate(
            name=f"Bench Supplier {number:04d}",
            country=country,
            categories=rng.sample(categories, rng.randint(1, 3)),
            rate_per_shipment=round(rng.uniform(0.5, 25.0), 2),
            currency=CURRENCY_BY_COUNTRY[country],
            status=Status.ACTIVE if rng.random() < 0.8 else Status.SUSPENDED,
            service_zone=rng.choice([None, "West Coast", "Aragón", "Nacional", "Internacional"]),
            contact_email=f"bench{number:04d}@example.test",
            notes=None,
        )
        updated_at = now - timedelta(days=rng.randint(0, 720), seconds=rng.randint(0, 86399))
        docs.append({**supplier.model_dump(mode="json"), "updated_at": updated_at.isoformat()})
    with suppliers_table() as table:
        table.insert_multiple(docs)


def seed_incidents(rng: random.Random, count: int, now: datetime) -> None:
    from app.database import incidents_table
    from app.incident_models import Branch, IncidentCategory, IncidentOrigin, IncidentRecord, IncidentStatus

    # Distribución de estados verosímil para un histórico: la mayoría cerradas.
    statuses = [IncidentStatus.OPEN] * 2 + [IncidentStatus.IN_PROGRESS] * 2 + [IncidentStatus.RESOLVED] * 5 + [
        IncidentStatus.DISCARDED
    ]
    docs = []
    for number in range(1, count + 1):
        created_at = now - timedelta(days=rng.randint(0, 365), seconds=rng.randint(0, 86399))
        status = rng.choice(statuses)
        updated_at = created_at if status == IncidentStatus.OPEN else created_at + timedelta(hours=rng.randint(1, 240))
        record = IncidentRecord(
            title=f"Incidencia de benchmark {number:05d}",
            description="Registro sintético para medir el rendimiento de la API. " * rng.randint(1, 4),
            category=rng.choice(list(IncidentCategory)),
            origin=rng.choice(list(IncidentOrigin)),
            branch=rng.choice(list(Branch)),
            status=status,
            created_at=created_at,
            updated_at=min(updated_at, now),
        )
        docs.append(record.model_dump(mode="json", exclude_none=True))
    with incidents_table() as table:
        table.insert_multiple(docs)


def seed_user(password: str) -> str:
    from app.auth_models import Role, UserCreate
    from app.services.users import create_user

    user, _ = create_user(UserCreate(email=BENCH_EMAIL, password=password), role=Role.USER)
    return user.id


def seed_inventory(rng: random.Random, args: argparse.Namespace, now: datetime, user_uuid: str) -> None:
    from sqlmodel import Session

    from app.database import dispose_engine, get_engine
    from app.inventory_models import SKU, StockEntry, StockExit
    from app.inventory_schemas import ExitType, ProductCategory, Warehouse

    warehouses = list(Warehouse)
    with Session(get_engine()) as session:
        skus = [
            SKU(
                name=f"Bench product {number:04d}",
                sku=f"BENCH-{number:05d}",
                client_name=f"Bench Brand {rng.randint(1, 40):02d}",
                category=rng.choice(list(ProductCategory)).value,
                warehouse=warehouses[number % 2].value,
            )
            for number in range(1, args.skus + 1)
        ]
        session.add_all(skus)
        session.commit()
        sku_ids = [sku.id for sku in skus]
        sku_warehouse = {sku.id: sku.warehouse for sku in skus}

        # Entradas repartidas en el último año; cada una suma stock en un almacén (el del SKU el 90 % de las veces).
        stock: dict[tuple[int, str], int] = {}
        entries = []
        for number in range(1, args.entries + 1):
            sku_id = rng.choice(sku_ids)
            warehouse = sku_warehouse[sku_id] if rng.random() < 0.9 else rng.choice(warehouses).value
            quantity = rng.randint(10, 500)
            stock[(sku_id, warehouse)] = stock.get((sku_id, warehouse), 0) + quantity
            entries.append(
                StockEntry(
                    sku_id=sku_id,
                    quantity=quantity,
                    reference=f"BENCH-IN-{number:06d}",
                    warehouse=warehouse,
                    created_at=now - timedelta(days=rng.randint(30, 365), seconds=rng.randint(0, 86399)),
                    user_uuid=user_uuid,
                )
            )
        session.add_all(entries)

        # Salidas posteriores a las entradas y nunca mayores que el stock que queda (regla 2: nunca negativo).
        exits = []
        keys = list(stock)
        for number in range(1, args.exits + 1):
            key = rng.choice(keys)
            if stock[key] <= 0:
                continue
            quantity = rng.randint(1, min(stock[key], 200))
            stock[key] -= quantity
            exit_type = ExitType.DISPATCH if rng.random() < 0.95 else ExitType.LOSS
            exits.append(
                StockExit(
                    sku_id=key[0],
                    quantity=quantity,
                    exit_type=exit_type.value,
                    tracking_number=f"BENCH-TRK-{number:07d}" if exit_type == ExitType.DISPATCH else None,
                    warehouse=key[1],
                    created_at=now - timedelta(days=rng.randint(0, 29), seconds=rng.randint(0, 86399)),
                    user_uuid=user_uuid,
                )
            )
        session.add_all(exits)
        session.commit()
        print(f"  inventario: {len(skus)} SKUs, {len(entries)} entradas, {len(exits)} salidas")
    dispose_engine()


def main() -> None:
    args = parse_args()
    if len(args.password) < 8:
        sys.exit("La contraseña debe tener al menos 8 caracteres.")
    out = safe_out_dir(args.out)
    point_env_to(out)
    sys.stdout.reconfigure(encoding="utf-8")

    rng = random.Random(args.seed)
    # Fecha fija: el mismo `--seed` produce exactamente los mismos datos cualquier día.
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    started = time.perf_counter()
    print(f"Dataset de benchmark en {out}")
    seed_suppliers(rng, args.suppliers, now)
    print(f"  proveedores: {args.suppliers}")
    seed_incidents(rng, args.incidents, now)
    print(f"  incidencias: {args.incidents}")
    user_uuid = seed_user(args.password)
    print(f"  usuario: {BENCH_EMAIL}")
    seed_inventory(rng, args, now, user_uuid)
    print(f"Listo en {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
