"""Línea de comandos del pipeline semanal: la que ejecuta el `cron` de los lunes (PIPELINE_DESIGN.md §7).

Desde `services/api`, con la configuración de la API (`DATABASE_URL`, `TELEMETRY_ENVIRONMENT`):

    uv run --env-file .env python -m app.reporting                       # 2 últimas semanas completas
    uv run --env-file .env python -m app.reporting --week-start 2026-11-02 --weeks 4
    uv run --env-file .env python -m app.reporting --dry-run             # calcula y muestra, sin escribir nada

`cron` (lunes a las 06:00 UTC), en el contenedor de la API (que no instala el paquete: `python -m`):

    0 6 * * 1  docker compose -f docker-compose.prod.yml exec -T backend python -m app.reporting

Códigos de salida: 0 bien, 1 la ejecución ha fallado, 2 parámetros no válidos o ejecución ya en curso.
`--dry-run` solo lee `telemetry_events` y no registra ninguna ejecución.
"""

import argparse
import json
import logging
import sys
from datetime import date

from app.reporting.flow import (
    PipelineAlreadyRunning,
    PipelineRunFailed,
    compute_weekly_performance,
    run_weekly_performance,
)
from app.reporting.tables import ReportingStorageError
from app.reporting.weeks import DEFAULT_WEEKS, WindowError, resolve_window
from app.telemetry.config import get_environment


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.reporting",
        description="Reporte Semanal de Desempeño por Almacén y Cliente: recalcula semanas completas.",
    )
    parser.add_argument(
        "--week-start", type=date.fromisoformat, help="Semana más reciente a calcular (un lunes, YYYY-MM-DD)."
    )
    parser.add_argument(
        "--weeks", type=int, default=DEFAULT_WEEKS, help=f"Semanas hacia atrás (por defecto {DEFAULT_WEEKS})."
    )
    parser.add_argument("--dry-run", action="store_true", help="Calcula y muestra las filas sin escribir nada.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
    args = _parse_args(argv)
    try:
        if args.dry_run:
            window = resolve_window(args.week_start, args.weeks)
            computation = compute_weekly_performance(window, get_environment())
            preview = {**computation.stats(), "rows": computation.rows}
            print(json.dumps(preview, default=str, indent=2, ensure_ascii=False))
            return 0
        run = run_weekly_performance(week_start=args.week_start, weeks=args.weeks, trigger="cli")
    except (WindowError, PipelineAlreadyRunning) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (PipelineRunFailed, ReportingStorageError) as error:
        print(f"La ejecución ha fallado: {error}", file=sys.stderr)
        return 1
    print(
        f"Ejecución {run['id']} {run['status']}: semanas {run['week_from']} → {run['week_to']}, "
        f"{run['events_read']} eventos leídos ({run['events_rejected']} rechazados), "
        f"{run['rows_upserted']} filas escritas, {run['rows_deleted']} eliminadas, {run['duration_ms']} ms."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
