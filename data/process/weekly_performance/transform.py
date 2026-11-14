"""transform: validate → aggregate → controles de coherencia (PIPELINE_DESIGN.md §6 y §18.3).

Desde el Hito 6 el subflow `compute-weekly-warehouse-client-kpis` de `data/pipelines/pipeline.py` ejecuta esta
transformación por pasos: `prepare_events` (validate + semana ISO; la task cacheada `prepare-weekly-events`), una task
por KPI (`kpis.py`) y `check_consistency` sobre las filas. `transform_events` hace lo mismo en un solo paso (la
transformación de la Parte 2) y sirve de referencia de equivalencia. Funciones puras: el resultado depende **solo**
de los eventos de entrada, de las semanas pedidas y del código de este paquete. Por eso la clave de caché se
construye con tres piezas que este módulo expone:

- `fingerprint_events(raw)`: huella SHA-256 del contenido de los eventos extraídos (id, tipo, fecha y `tags`).
- las semanas (`weeks`) de la ventana;
- `CODE_VERSION`: huella SHA-256 del código fuente de este paquete. Si cambia una regla de validación o una fórmula,
  cambia la versión y ningún resultado cacheado con el código anterior se reutiliza.

Controles de coherencia (`check_consistency`), además de las reglas por fila de `validate`:

| Control | Qué detecta |
| --- | --- |
| Una fila por `(warehouse, client_id, week_start)` | Errores de agrupación (filas duplicadas) |
| Semana de cada fila dentro de la ventana | Ventanas mal resueltas o eventos fuera de rango |
| Contadores enteros ≥ 0 | Valores fuera de rango |
| `discrepancy_rate` = `discrepancy / outbound` a 4 decimales, 0 sin pedidos | División por cero, fórmula mal aplicada |
| Totales de las filas = totales de los eventos válidos de la ventana | Eventos perdidos o contados dos veces |

Un resultado incoherente lanza `InconsistentResultError`: la ejecución falla y **no se carga nada** (nunca se publica
un número que no cuadra con su origen).
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from data.process.weekly_performance.aggregate import RATE_DECIMALS, aggregate_rows, week_start_series, weekly_events
from data.process.weekly_performance.events import DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT
from data.process.weekly_performance.validate import WAREHOUSES, validate_events

COUNT_COLUMNS = ("inbound_units_count", "outbound_orders_count", "stockout_events_count", "discrepancy_events_count")
_RATE_TOLERANCE = 0.5 * 10**-RATE_DECIMALS + 1e-12


def _code_version() -> str:
    """Huella del código fuente del paquete (todos sus `.py`, en orden): cambia con cualquier cambio de lógica."""
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


CODE_VERSION = _code_version()


class InconsistentResultError(ValueError):
    """Las filas calculadas no cuadran con los eventos de origen. `problems` lista cada incoherencia encontrada."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("Resultado incoherente: " + "; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Transformation:
    """Filas del reporte listas para cargar y recuentos de calidad para el registro de la ejecución."""

    rows: list[dict]
    events_read: dict[str, int] = field(default_factory=dict)
    rejected: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_read(self) -> int:
        return sum(self.events_read.values())

    @property
    def total_rejected(self) -> int:
        return sum(sum(by_reason.values()) for by_reason in self.rejected.values())


def fingerprint_events(raw: pd.DataFrame) -> str:
    """SHA-256 del contenido de los eventos extraídos, independiente del orden de las filas.

    Dos extracciones con los mismos eventos (mismos `id`, tipos, fechas y `tags`) dan la misma huella; un evento nuevo,
    tardío o distinto en cualquier campo la cambia.
    """
    records = sorted(
        (
            [str(row.id), str(row.event_type), str(row.timestamp), json.dumps(row.tags, sort_keys=True, default=str)]
            for row in raw[["id", "event_type", "timestamp", "tags"]].itertuples(index=False)
        ),
        key=lambda record: record[0],
    )
    payload = json.dumps(records, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _expected_totals(valid: pd.DataFrame, weeks: list[date]) -> dict[str, int]:
    if valid.empty:
        return dict.fromkeys(COUNT_COLUMNS, 0)
    in_window = valid[week_start_series(valid["timestamp"]).isin(weeks)]
    by_type = in_window["event_type"]
    return {
        "inbound_units_count": int(in_window.loc[by_type.eq(INBOUND), "quantity"].sum()),
        "outbound_orders_count": int(by_type.eq(OUTBOUND).sum()),
        "stockout_events_count": int(by_type.eq(STOCKOUT).sum()),
        "discrepancy_events_count": int(by_type.eq(DISCREPANCY).sum()),
    }


def check_consistency(rows: list[dict], valid: pd.DataFrame, weeks: Iterable[date]) -> None:
    """`InconsistentResultError` si alguna fila incumple las reglas del reporte o los totales no cuadran."""
    weeks = list(weeks)
    problems: list[str] = []
    keys = [(row["warehouse"], row["client_id"], row["week_start"]) for row in rows]
    if len(keys) != len(set(keys)):
        problems.append("hay filas repetidas para la misma (warehouse, client_id, week_start)")
    for row in rows:
        label = f"{row['warehouse']}/{row['client_id']}/{row['week_start']}"
        if row["week_start"] not in weeks:
            problems.append(f"{label}: semana fuera de la ventana")
        if row["warehouse"] not in WAREHOUSES:
            problems.append(f"{label}: almacén no válido")
        for column in COUNT_COLUMNS:
            value = row[column]
            if type(value) is not int or value < 0:
                problems.append(f"{label}: {column} = {value!r} no es un entero ≥ 0")
        outbound, discrepancies = row["outbound_orders_count"], row["discrepancy_events_count"]
        exact_rate = discrepancies / outbound if outbound > 0 else 0.0
        # Redondeo a 4 decimales: como mucho media unidad del último decimal (numpy y Python desempatan distinto).
        rate = row["discrepancy_rate"]
        if not isinstance(rate, float) or abs(rate - exact_rate) > _RATE_TOLERANCE:
            problems.append(f"{label}: discrepancy_rate {rate!r} ≠ {exact_rate:.6f}")
    expected = _expected_totals(valid, weeks)
    for column in COUNT_COLUMNS:
        total = sum(row[column] for row in rows)
        if total != expected[column]:
            problems.append(f"total de {column}: filas {total} ≠ eventos válidos {expected[column]}")
    if problems:
        raise InconsistentResultError(problems)


@dataclass(frozen=True)
class PreparedEvents:
    """Entrada común de las tasks de KPI (Hito 6): eventos válidos de la ventana con su `week_start`.

    `events` tiene las columnas de `validate.VALID_COLUMNS` más `week_start`; `events_read` y `rejected` son los
    recuentos de calidad para el registro de la ejecución.
    """

    events: pd.DataFrame
    events_read: dict[str, int] = field(default_factory=dict)
    rejected: dict[str, dict[str, int]] = field(default_factory=dict)


def prepare_events(raw: pd.DataFrame, weeks: Iterable[date]) -> PreparedEvents:
    """validate → semana ISO de cada evento → solo las semanas de la ventana. Es la etapa que cachea Prefect."""
    validated = validate_events(raw)
    return PreparedEvents(
        events=weekly_events(validated.valid, weeks),
        events_read=validated.events_read,
        rejected=validated.rejected,
    )


def transform_events(raw: pd.DataFrame, weeks: Iterable[date]) -> Transformation:
    """validate → aggregate → check_consistency en un solo paso. Sin efectos secundarios.

    Es la transformación de la Parte 2; desde el Hito 6 el pipeline la ejecuta por pasos (una task por KPI en el
    subflow `compute-weekly-warehouse-client-kpis`) con el mismo resultado. Se conserva como referencia de
    equivalencia y para quien necesite el cálculo completo sin Prefect.
    """
    weeks = list(weeks)
    validated = validate_events(raw)
    rows = aggregate_rows(validated.valid, weeks)
    check_consistency(rows, validated.valid, weeks)
    return Transformation(rows=rows, events_read=validated.events_read, rejected=validated.rejected)
