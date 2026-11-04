"""Rondas alternas «antes / después» para que la deriva del equipo no sesgue la comparación (`CACHING_REPORT.md`).

Con dos APIs arrancadas a la vez sobre copias del mismo dataset (una sin caché y otra con caché), mide los mismos
endpoints en rondas alternas (antes, después, antes, después…). Cada ronda: calentamiento + N peticiones secuenciales
por endpoint, latencia en el cliente. El resultado de cada endpoint es la **mediana de las medianas** de sus rondas y
el p95 de todas las peticiones juntas.

Uso (desde la raíz del repo):

    python audit/caching/interleave.py --before http://127.0.0.1:8032 --after http://127.0.0.1:8031 \
        --email benchmark@trackflow.test --password <contraseña> --out audit/caching/results/interleaved.json
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_api import ENDPOINTS, Client, login, measure_sequential, summary  # noqa: E402

# Endpoints cacheados y controles (mismo código en las dos APIs): si un control cambia, es ruido del equipo.
DEFAULT_ENDPOINTS = [
    "incidents_summary",
    "inventory_products",
    "inventory_products_la",
    "health",
    "suppliers_list",
    "incident_detail",
    "inventory_product_detail",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--only", nargs="*", default=DEFAULT_ENDPOINTS)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    clients = {
        "before": Client(args.before, login(args.before, args.email, args.password)),
        "after": Client(args.after, login(args.after, args.email, args.password)),
    }
    paths = dict(ENDPOINTS)
    samples = {name: {"before": [], "after": []} for name in args.only}
    medians = {name: {"before": [], "after": []} for name in args.only}

    for round_number in range(1, args.rounds + 1):
        for side in ("before", "after"):
            for name in args.only:
                times, status, _ = measure_sequential(clients[side], paths[name], args.warmup, args.requests)
                if status != 200:
                    sys.exit(f"{side} {name}: estado {status}")
                samples[name][side].extend(times)
                medians[name][side].append(round(statistics.median(times), 3))
        print(f"Ronda {round_number}/{args.rounds} terminada", flush=True)
        time.sleep(0.5)

    results = []
    for name in args.only:
        before = statistics.median(medians[name]["before"])
        after = statistics.median(medians[name]["after"])
        results.append(
            {
                "name": name,
                "path": paths[name],
                "before": {"round_medians_ms": medians[name]["before"], "median_ms": round(before, 3),
                           "pooled": summary(samples[name]["before"])},
                "after": {"round_medians_ms": medians[name]["after"], "median_ms": round(after, 3),
                          "pooled": summary(samples[name]["after"])},
                "change_pct": round((after - before) / before * 100, 1),
            }
        )
        print(f"{name:26} antes {before:8.2f} ms  después {after:8.2f} ms  ({results[-1]['change_pct']:+.1f} %)")

    report = {
        "rounds": args.rounds,
        "requests_per_round": args.requests,
        "warmup_per_round": args.warmup,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Resultados en {args.out}")


if __name__ == "__main__":
    main()
