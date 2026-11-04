"""Prueba de carga de los endpoints de lectura de la API (`CACHING_REPORT.md`). Solo biblioteca estándar.

Para cada endpoint hace `--warmup` peticiones que no cuentan y `--requests` peticiones medidas, una detrás de otra y
con los mismos parámetros, sobre una conexión HTTP persistente. Mide:

- **cliente**: tiempo de ida y vuelta (`time.perf_counter`) de cada petición, cuerpo incluido;
- **servidor**: el tiempo que registra `RequestTimingMiddleware` (`trackflow.api.timing`) y sus consultas SQL, leídos
  del log de uvicorn (`--server-log`), si se indica.

Con `--concurrency N`, cada endpoint se mide además con N hilos a la vez (una conexión por hilo) y se anota el
rendimiento en peticiones por segundo.

Uso (API arrancada con las bases de `seed_benchmark.py` y su salida redirigida a un fichero):

    python audit/caching/bench_api.py --email benchmark@trackflow.test --password <contraseña> \
        --server-log <log de uvicorn> --out audit/caching/results/before.json
"""

import argparse
import http.client
import json
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

# Endpoints de lectura medidos, con parámetros fijos. Los ids existen en el dataset de benchmark.
ENDPOINTS = [
    ("health", "/health"),
    ("auth_me", "/auth/me"),
    ("profiles_me", "/profiles/me"),
    ("suppliers_list", "/suppliers"),
    ("suppliers_filtered", "/suppliers?country=Spain&category=carrier_last_mile"),
    ("supplier_detail", "/suppliers/250"),
    ("incidents_list", "/api/incidents"),
    ("incidents_filtered", "/api/incidents?status=open&branch=central"),
    ("incidents_summary", "/api/incidents/summary"),
    ("incident_detail", "/api/incidents/2500"),
    ("inventory_products", "/inventory/products"),
    ("inventory_products_la", "/inventory/products?warehouse=LA"),
    ("inventory_product_detail", "/inventory/products/500"),
    ("inventory_orders", "/inventory/orders"),
    ("inventory_orders_sku", "/inventory/orders?sku_id=500"),
]

# Endpoints que tardan más de un segundo por petición con el dataset de benchmark: se miden con
# `--heavy-requests` peticiones para que la prueba termine en minutos.
HEAVY = {"inventory_orders"}

TIMING_LINE = re.compile(r"trackflow\.api\.timing: (\w+) (\S+) (\d{3}) ([\d.]+) ms(?: sql=(\d+))?")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=200, help="Peticiones medidas por endpoint")
    parser.add_argument("--warmup", type=int, default=10, help="Peticiones de calentamiento por endpoint")
    parser.add_argument("--heavy-requests", type=int, default=20, help="Peticiones medidas de los endpoints lentos")
    parser.add_argument("--concurrency", type=int, default=0, help="Hilos para la medición concurrente (0 = no)")
    parser.add_argument("--only", nargs="*", help="Nombres de endpoints a medir (por defecto, todos)")
    parser.add_argument("--server-log", type=Path, help="Fichero con la salida de uvicorn (log de tiempos)")
    parser.add_argument("--label", default="", help="Etiqueta de la medición (p. ej. «antes» o «después»)")
    parser.add_argument("--out", type=Path, required=True, help="Fichero JSON de resultados")
    return parser.parse_args()


class Client:
    """Conexión HTTP persistente con el Bearer token."""

    def __init__(self, base_url: str, token: str | None = None):
        parts = urlsplit(base_url)
        self.host, self.port = parts.hostname, parts.port or 80
        self.conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
        self.headers = {"Accept": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        headers = dict(self.headers)
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            self.conn.request(method, path, body=payload, headers=headers)
            response = self.conn.getresponse()
        except (ConnectionError, http.client.RemoteDisconnected):
            # uvicorn cierra las conexiones inactivas a los 5 s: se reabre una vez y se repite.
            self.conn.close()
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
            self.conn.request(method, path, body=payload, headers=headers)
            response = self.conn.getresponse()
        return response.status, response.read()


def login(base_url: str, email: str, password: str) -> str:
    status, body = Client(base_url).request("POST", "/auth/login", {"email": email, "password": password})
    if status != 200:
        sys.exit(f"Login fallido ({status}). ¿Está la API arrancada con las bases de benchmark?")
    return json.loads(body)["access_token"]


def summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, round(0.95 * len(ordered)) - 1)
    return {
        "mean": round(statistics.fmean(ordered), 3),
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


def read_new_lines(log: Path | None, offset: int) -> tuple[list[str], int]:
    if log is None or not log.exists():
        return [], offset
    with log.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
    return data.decode("utf-8", errors="replace").splitlines(), offset + len(data)


def server_stats(lines: list[str], skip: int) -> dict | None:
    """Tiempos y consultas SQL del log de tiempos, sin las primeras `skip` líneas (calentamiento)."""
    matches = [TIMING_LINE.search(line) for line in lines]
    rows = [m for m in matches if m and m.group(1) == "GET"][skip:]
    if not rows:
        return None
    durations = [float(m.group(4)) for m in rows]
    queries = [int(m.group(5) or 0) for m in rows]
    return {"ms": summary(durations), "sql_per_request": round(statistics.fmean(queries), 2), "lines": len(rows)}


def measure_sequential(client: Client, path: str, warmup: int, count: int) -> tuple[list[float], int, int]:
    size = 0
    status = 0
    for _ in range(warmup):
        status, body = client.request("GET", path)
    times = []
    for _ in range(count):
        start = time.perf_counter()
        status, body = client.request("GET", path)
        times.append((time.perf_counter() - start) * 1000)
        size = len(body)
    return times, status, size


def measure_concurrent(base_url: str, token: str, path: str, threads: int, count: int) -> dict:
    per_thread = max(1, count // threads)
    times: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        client = Client(base_url, token)
        local = []
        for _ in range(per_thread):
            start = time.perf_counter()
            client.request("GET", path)
            local.append((time.perf_counter() - start) * 1000)
        with lock:
            times.extend(local)

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    started = time.perf_counter()
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    elapsed = time.perf_counter() - started
    return {"threads": threads, "requests": len(times), "rps": round(len(times) / elapsed, 1), "ms": summary(times)}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def main() -> None:
    args = parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    token = login(args.base_url, args.email, args.password)
    client = Client(args.base_url, token)
    endpoints = [(name, path) for name, path in ENDPOINTS if not args.only or name in args.only]

    _, offset = read_new_lines(args.server_log, 0)
    results = []
    for name, path in endpoints:
        count = min(args.requests, args.heavy_requests) if name in HEAVY else args.requests
        warmup = min(args.warmup, 2) if name in HEAVY else args.warmup
        times, status, size = measure_sequential(client, path, warmup, count)
        time.sleep(0.3)  # deja que uvicorn vacíe su salida antes de leer el log
        lines, offset = read_new_lines(args.server_log, offset)
        row = {
            "name": name,
            "path": path,
            "status": status,
            "bytes": size,
            "requests": count,
            "warmup": warmup,
            "client_ms": summary(times),
            "server": server_stats(lines, warmup),
        }
        if args.concurrency:
            row["concurrent"] = measure_concurrent(args.base_url, token, path, args.concurrency, count)
            _, offset = read_new_lines(args.server_log, offset)
        results.append(row)
        server = row["server"]["ms"]["median"] if row["server"] else float("nan")
        print(
            f"{name:26} {status} {size:>9} B  cliente mediana {row['client_ms']['median']:8.2f} ms"
            f"  p95 {row['client_ms']['p95']:8.2f} ms  servidor mediana {server:8.2f} ms",
            flush=True,
        )

    report = {
        "label": args.label,
        "commit": git_commit(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "requests_per_endpoint": args.requests,
        "heavy_requests": args.heavy_requests,
        "warmup_per_endpoint": args.warmup,
        "concurrency": args.concurrency,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Resultados en {args.out}")


if __name__ == "__main__":
    main()
