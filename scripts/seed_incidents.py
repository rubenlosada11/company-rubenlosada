#!/usr/bin/env python3
"""Seed del gestor de incidencias: carga el CSV histórico del analizador en la base de la API.

Cada fila se valida con la lógica compartida del analizador (`validar_registro`), se transforma con los mapeos de
CONTEXT-gestor-incidencias.es.md (`gestor.transformar_fila`) y pasa por el mismo modelo que usa la API antes de
guardarse. Las filas no válidas se descartan y se listan en consola. Es idempotente: el `incident_id` del CSV se
guarda como referencia interna y una fila ya cargada no se vuelve a insertar.

Necesita el entorno de la API (TinyDB y los modelos). Desde la raíz del repositorio:

    uv run --project services/api python scripts/seed_incidents.py [fichero.csv]

Ejecútalo con la API parada: el candado de TinyDB no protege entre procesos. Los correos de clientes
(`customer_email`) nunca se imprimen ni se guardan.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSV_POR_DEFECTO = Path(__file__).resolve().parent / "incidents-trackflow.csv"

# El paquete compartido se usa directamente desde el monorepo, igual que en analyze.py.
sys.path.insert(0, str(RAIZ / "packages" / "analisis-incidencias" / "src"))

from analisis_incidencias import REGLAS, ErrorAnalisis, Fila, leer_csv, validar_registro  # noqa: E402
from analisis_incidencias.gestor import CATEGORIAS, ESTADOS, ErrorTransformacion, transformar_fila  # noqa: E402

try:
    from pydantic import ValidationError
    from tinydb.table import Table

    from app.database import get_incidents_db_path, incidents_table
    from app.incident_models import IncidentRecord
    from app.services.incidents import insert_incident
except ImportError as error:  # Python del sistema, sin el entorno de la API
    sys.stderr.reconfigure(encoding="utf-8")
    print(f"Error: falta el entorno de la API ({error.name}).", file=sys.stderr)
    print("Ejecuta desde la raíz:  uv run --project services/api python scripts/seed_incidents.py", file=sys.stderr)
    raise SystemExit(2) from None


@dataclass
class Descartada:
    linea: int
    incident_id: str
    motivos: list[str]


@dataclass
class ResultadoSeed:
    leidas: int = 0
    validas: int = 0
    insertadas: int = 0
    duplicadas: int = 0
    errores: int = 0
    invalidas: list[Descartada] = field(default_factory=list)


def preparar(fila: Fila) -> IncidentRecord | list[str]:
    """Fila del CSV → registro listo para guardar, o los motivos por los que se descarta."""
    codigos = validar_registro(fila.datos, fila.columnas_ok)
    if codigos:
        return [REGLAS[codigo] for codigo in codigos]
    try:
        return IncidentRecord.model_validate(transformar_fila(fila.datos))
    except ErrorTransformacion as error:
        return [str(error)]
    except ValidationError as error:
        return [str(detalle["msg"]).removeprefix("Value error, ") for detalle in error.errors()]


def seed(table: Table, filas: list[Fila]) -> ResultadoSeed:
    resultado = ResultadoSeed(leidas=len(filas))
    existentes = {doc["source_id"] for doc in table.all() if doc.get("source_id")}

    for fila in filas:
        registro = preparar(fila)
        if isinstance(registro, list):
            resultado.invalidas.append(Descartada(fila.linea, fila.datos.get("incident_id", ""), registro))
            continue
        resultado.validas += 1
        if registro.source_id in existentes:
            resultado.duplicadas += 1
            continue
        try:
            insert_incident(table, registro)
        except Exception as error:  # un fallo al escribir una fila no detiene el resto
            resultado.errores += 1
            print(f"  ! línea {fila.linea} ({registro.source_id}): {type(error).__name__}", file=sys.stderr)
            continue
        existentes.add(registro.source_id)
        resultado.insertadas += 1

    return resultado


def totales_del_csv(table: Table) -> tuple[Counter, Counter]:
    """Conteos por estado y categoría de las incidencias de la base que vienen del CSV."""
    docs = [doc for doc in table.all() if doc.get("source_id")]
    return Counter(doc["status"] for doc in docs), Counter(doc["category"] for doc in docs)


def imprimir(resultado: ResultadoSeed, por_estado: Counter, por_categoria: Counter, total: int) -> None:
    if resultado.invalidas:
        print("Registros descartados:")
        for descartada in resultado.invalidas:
            identificador = descartada.incident_id or "sin id"
            print(f"  - línea {descartada.linea} · {identificador}: {'; '.join(descartada.motivos)}")
        print()

    print("Seed completado.")
    for etiqueta, valor in (
        ("Filas leídas", resultado.leidas),
        ("Válidas", resultado.validas),
        ("Insertadas", resultado.insertadas),
        ("Duplicadas", resultado.duplicadas),
        ("Inválidas", len(resultado.invalidas)),
        ("Errores", resultado.errores),
    ):
        print(f"  {etiqueta + ':':<14}{valor:>4}")

    print()
    print(f"Incidencias en la base: {total} ({sum(por_estado.values())} del CSV)")
    print("  Por estado (CSV):    " + " · ".join(f"{e} {por_estado[e]}" for e in ESTADOS if por_estado[e]))
    print("  Por categoría (CSV): " + " · ".join(f"{c} {por_categoria[c]}" for c in CATEGORIAS if por_categoria[c]))


def main(argv: list[str] | None = None) -> int:
    # Si la salida va a una tubería o fichero, Windows usa cp1252 y los acentos se estropean.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Carga el CSV histórico de incidencias en el gestor.")
    parser.add_argument("csv", nargs="?", type=Path, default=CSV_POR_DEFECTO, help="CSV del analizador de incidencias")
    args = parser.parse_args(argv)

    try:
        filas = leer_csv(args.csv)
    except ErrorAnalisis as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"CSV:           {args.csv}")
    print(f"Base de datos: {get_incidents_db_path()}")
    print()
    with incidents_table() as table:
        resultado = seed(table, filas)
        por_estado, por_categoria = totales_del_csv(table)
        total = len(table)
    imprimir(resultado, por_estado, por_categoria, total)
    return 1 if resultado.errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
