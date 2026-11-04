"""Carga mixta de lecturas y escrituras para medir aciertos, fallos e invalidaciones de la caché (`CACHING_REPORT.md`).

Simula el uso del backoffice sobre una **copia** del dataset de `seed_benchmark.py` (se niega a usar
`services/api/db`): consultas del listado del inventario (con y sin filtro de almacén) y del resumen del gestor,
intercaladas con escrituras que los invalidan (entradas de stock, altas y cambios de estado de incidencias). Todo en
proceso con `TestClient`, sin red.

Mide, por caché: aciertos, fallos e invalidaciones (contadores de `TTLCache.stats()`), y la latencia de las lecturas
que fueron acierto y de las que fueron fallo (incluidas las que siguen a una escritura). Semilla fija: misma secuencia.

Uso (desde la raíz del repo):

    uv run --project services/api python audit/caching/workload.py <copia del dataset> --out audit/caching/results/workload.json
"""

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DB_DIR = (REPO_ROOT / "services" / "api" / "db").resolve()

# Peso de cada operación en la mezcla (lecturas cacheadas, otras lecturas y escrituras que invalidan).
# Proporción supuesta (no medida en producción): unas 9 lecturas por cada escritura.
OPERATIONS = [
    ("GET /inventory/products", 35),
    ("GET /inventory/products?warehouse=LA", 10),
    ("GET /inventory/products?warehouse=ZGZ", 10),
    ("GET /api/incidents/summary", 35),
    ("POST /inventory/orders/inbound", 5),
    ("POST /api/incidents", 2),
    ("PATCH /api/incidents/{id}/status", 3),
]
CACHED_PATHS = {
    "/inventory/products": "inventory.products",
    "/api/incidents/summary": "incidents.summary",
}
INCIDENT = {
    "title": "Incidencia de la carga mixta",
    "description": "Registro sintético de la medición de la caché.",
    "category": "carrier_issue",
    "origin": "internal",
    "branch": "central",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data", type=Path, help="Copia del dataset de benchmark (se modifica)")
    parser.add_argument("--operations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "mean": round(statistics.fmean(ordered), 3),
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[max(0, round(0.95 * len(ordered)) - 1)], 3),
    }


def main() -> None:
    args = parse_args()
    data = args.data.resolve()
    if data == REAL_DB_DIR or REAL_DB_DIR in data.parents or not (data / "inventory.db").exists():
        sys.exit("Indica una copia del dataset de benchmark, nunca services/api/db.")
    os.environ.update(
        SECRET_KEY="workload-secret-key-0123456789-abcdefghij",
        SUPPLIERS_DB_PATH=str(data / "suppliers.json"),
        INCIDENTS_DB_PATH=str(data / "incidents.json"),
        AUTH_DB_PATH=str(data / "auth.json"),
        DATABASE_URL=f"sqlite:///{(data / 'inventory.db').as_posix()}",
    )
    sys.stdout.reconfigure(encoding="utf-8")

    import logging

    from fastapi.testclient import TestClient

    from app.cache import all_caches, reset_all
    from app.main import app
    from app.security import create_access_token
    from app.services.users import list_users

    logging.getLogger("trackflow").setLevel(logging.WARNING)  # sin una línea de log por petición

    user = list_users()[0]
    client = TestClient(app, headers={"Authorization": f"Bearer {create_access_token(user.id)[0]}"})
    rng = random.Random(args.seed)
    names, weights = zip(*OPERATIONS, strict=True)
    open_incidents = [i["id"] for i in client.get("/api/incidents", params={"status": "open"}).json()]
    reset_all()

    timings: dict[str, dict[str, list[float]]] = {}
    for _ in range(args.operations):
        operation = rng.choices(names, weights)[0]
        method, target = operation.split(" ", 1)
        start = time.perf_counter()
        if operation == "POST /inventory/orders/inbound":
            body = {"sku_id": rng.randint(1, 1000), "quantity": rng.randint(1, 50), "reference": "WORKLOAD"}
            response = client.post("/inventory/orders/inbound", json=body)
        elif operation == "PATCH /api/incidents/{id}/status" and open_incidents:
            incident_id = open_incidents.pop()
            response = client.patch(f"/api/incidents/{incident_id}/status", json={"status": "in_progress"})
        elif operation == "POST /api/incidents":
            response = client.post("/api/incidents", json=INCIDENT)
        elif method == "GET":
            path = target.split("?", 1)[0]
            cache = all_caches()[CACHED_PATHS[path]]
            before = cache.stats()
            response = client.get(target)
            elapsed = (time.perf_counter() - start) * 1000
            kind = "hit" if cache.stats().hits > before.hits else "miss"
            timings.setdefault(cache.name, {"hit": [], "miss": []})[kind].append(elapsed)
            assert response.status_code == 200, response.text
            continue
        else:
            continue
        assert response.status_code in (200, 201), response.text

    report = {
        "operations": args.operations,
        "seed": args.seed,
        "mix": dict(OPERATIONS),
        "caches": {
            name: {
                "ttl_seconds": cache.ttl_seconds,
                "hits": cache.stats().hits,
                "misses": cache.stats().misses,
                "invalidations": cache.stats().invalidations,
                "hit_ratio": round(cache.stats().hit_ratio, 3),
                "hit_ms": summary(timings.get(name, {}).get("hit", [])),
                "miss_ms": summary(timings.get(name, {}).get("miss", [])),
            }
            for name, cache in all_caches().items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, row in report["caches"].items():
        print(
            f"{name:20} TTL {row['ttl_seconds']:>4}s  aciertos {row['hits']:4}  fallos {row['misses']:4}"
            f"  invalidaciones {row['invalidations']:4}  ratio {row['hit_ratio']:.1%}"
            f"  acierto mediana {row['hit_ms'].get('median')} ms  fallo mediana {row['miss_ms'].get('median')} ms"
        )
    print(f"Resultados en {args.out}")


if __name__ == "__main__":
    main()
