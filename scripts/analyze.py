#!/usr/bin/env python3
"""Analizador de incidencias de TrackFlow (interfaz de línea de comandos).

Lee el CSV exportado del helpdesk, muestra el informe en consola y ofrece
exportarlo a CSV. La validación y las métricas viven en el paquete compartido
`packages/analisis-incidencias`, que también usa la API (`services/api`).

Uso:
    python analyze.py incidents-trackflow.csv [--output results.csv]

El procesamiento es 100 % local. Los correos de clientes (`customer_email`)
nunca se imprimen ni se exportan.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable

# El paquete compartido se usa directamente desde el monorepo, sin instalarlo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "analisis-incidencias" / "src"))

from analisis_incidencias import (  # noqa: E402
    REGLAS,
    REGLAS_COMPLEMENTARIAS,
    ErrorAnalisis,
    analizar,
    generar_csv_bytes,
    leer_csv,
    porcentaje,
)
from analisis_incidencias.dominio import ETIQUETAS_PUNTUACION, PUNTUACION_MAX, PUNTUACIONES  # noqa: E402

# ---------------------------------------------------------------------------
# Informe de consola
# ---------------------------------------------------------------------------

ANCHO = 64
ANCHO_ETIQUETA = 38
SANGRIA_LISTA = 5  # ancho de "  ├─ "


def _lider(etiqueta: str, valor: str, ancho: int = ANCHO_ETIQUETA) -> str:
    puntos = "." * max(2, ancho - len(etiqueta))
    return f"{etiqueta} {puntos} {valor}"


def _lista(pares: list[tuple[str, str]]) -> list[str]:
    if not pares:
        return ["  (ninguno)"]
    return [
        f"  {'└─' if i == len(pares) - 1 else '├─'} {_lider(etiqueta, valor)}"
        for i, (etiqueta, valor) in enumerate(pares)
    ]


def _conteos(conteo: dict[str, int], total: int) -> list[str]:
    pares = []
    for clave, n in conteo.items():
        pct = porcentaje(n, total)
        pares.append((clave, f"{n:>3}" + (f"  ({pct:5.1f}%)" if pct is not None else "")))
    return _lista(pares)


def _tabla(cabecera: list[str], filas: list[list[str]]) -> list[str]:
    anchos = [max(len(str(x)) for x in col) for col in zip(cabecera, *filas)]
    lineas = []
    for i, fila in enumerate([cabecera, *filas]):
        celdas = [str(fila[0]).ljust(anchos[0])] + [str(c).rjust(a) for c, a in zip(fila[1:], anchos[1:])]
        lineas.append("  " + "  ".join(celdas))
        if i == 0:
            lineas.append("  " + "  ".join("-" * a for a in anchos))
    return lineas


def _tabla_cruce(titulo_fila: str, cruce: dict[str, dict[str, int]]) -> list[str]:
    columnas = list(next(iter(cruce.values())))
    filas = [[f, *(m[c] for c in columnas), sum(m.values())] for f, m in cruce.items()]
    return _tabla([titulo_fila, *columnas, "TOTAL"], filas)


def _tabla_satisfaccion(titulo_fila: str, grupos: dict[str, dict]) -> list[str]:
    filas = [
        [g, s["cerradas"], s["con_puntuacion"], f"{s['media']:.2f}" if s["media"] is not None else "—"]
        for g, s in grupos.items()
    ]
    return _tabla([titulo_fila, "Cerradas", "Con puntuación", "Media"], filas)


def _etiqueta_semana(clave: str) -> str:
    anio, semana = clave.split("-S")
    lunes = date.fromisocalendar(int(anio), int(semana), 1)
    domingo = date.fromisocalendar(int(anio), int(semana), 7)
    return f"{clave} ({lunes:%d/%m}–{domingo:%d/%m})"


def formatear_informe(resultado: dict) -> str:
    """Construye el informe de consola a partir del resultado de `analizar`."""
    totales = resultado["totales"]
    validos = totales["validos"]
    satisf = resultado["satisfaccion"]
    por_fecha = resultado["por_fecha"]
    lineas: list[str] = []
    seccion = lambda titulo: lineas.extend(["", titulo])  # noqa: E731

    lineas += [
        "=" * ANCHO,
        "  TRACKFLOW — ANÁLISIS DE INCIDENCIAS",
        f"  Fichero: {resultado['archivo']}",
        "=" * ANCHO,
        "",
        _lider("TOTAL DE REGISTROS", f"{totales['procesados']:>3}", ANCHO_ETIQUETA + SANGRIA_LISTA),
        *_lista([
            ("Registros válidos", f"{validos:>3}"),
            ("Inválidos / incompletos", f"{totales['invalidos']:>3}"),
        ]),
    ]

    seccion("REGISTROS INVÁLIDOS POR REGLA")
    reglas = [
        (REGLAS[c] + (" *" if c in REGLAS_COMPLEMENTARIAS else ""), f"{n:>3}")
        for c, n in resultado["invalidos_por_regla"].items()
        if n
    ]
    lineas += _lista(reglas)
    if any(c in REGLAS_COMPLEMENTARIAS and n for c, n in resultado["invalidos_por_regla"].items()):
        lineas.append("  * Regla complementaria (campo obligatorio según la tabla del CONTEXT).")
    if sum(resultado["invalidos_por_regla"].values()) > totales["invalidos"]:
        lineas.append("  Nota: algunos registros incumplen varias reglas y cuentan en cada una.")
    if resultado["registros_invalidos"]:
        lineas += ["", "  Detalle (sin datos personales):"]
        for r in resultado["registros_invalidos"]:
            motivos = ", ".join(REGLAS[c] for c in r["reglas"])
            lineas.append(f"    · Línea {r['linea']:>4} · {r['incident_id'] or '(sin ID)'} · {motivos}")

    seccion("INCIDENCIAS POR CATEGORÍA (registros válidos)")
    lineas += _conteos(resultado["por_categoria"], validos)
    seccion("INCIDENCIAS POR ESTADO (registros válidos)")
    lineas += _conteos(resultado["por_estado"], validos)
    seccion("INCIDENCIAS POR PAÍS (registros válidos)")
    lineas += _conteos(resultado["por_pais"], validos)
    seccion("INCIDENCIAS POR TIPO DE CLIENTE (registros válidos)")
    lineas += _conteos(resultado["por_tipo_cliente"], validos)
    seccion("INCIDENCIAS POR TRANSPORTISTA (registros válidos)")
    lineas += _conteos(resultado["por_transportista"], validos)

    seccion("EVOLUCIÓN TEMPORAL (registros válidos)")
    lineas.append("  Por mes:")
    lineas += _conteos(por_fecha["mes"], validos)
    lineas.append("  Por trimestre:")
    lineas += _conteos(por_fecha["trimestre"], validos)
    lineas.append("  Por semana (ISO):")
    semanas = {_etiqueta_semana(k): v for k, v in por_fecha["semana"].items()}
    lineas += _conteos(semanas, validos)
    lineas.append("  Por día de la semana:")
    lineas += _conteos(por_fecha["dia_semana"], validos)

    seccion("PAÍS × CATEGORÍA (registros válidos)")
    lineas += _tabla_cruce("País", resultado["cruces"]["pais_categoria"])
    seccion("TRANSPORTISTA × CATEGORÍA (registros válidos)")
    lineas += _tabla_cruce("Transportista", resultado["cruces"]["transportista_categoria"])
    seccion("TRANSPORTISTA × ESTADO (registros válidos)")
    lineas += _tabla_cruce("Transportista", resultado["cruces"]["transportista_estado"])

    seccion("ÍNDICE DE SATISFACCIÓN (incidencias cerradas)")
    media = f"{satisf['media']:.2f}" if satisf["media"] is not None else "—"
    lineas += [
        f"  Con puntuación: {satisf['con_puntuacion']} de {satisf['cerradas']}",
        f"  Media: {media} / {PUNTUACION_MAX:.2f}",
        *_lista([
            (f"{p} ({ETIQUETAS_PUNTUACION[p]})", f"{satisf['distribucion'][str(p)]:>3}")
            for p in PUNTUACIONES
        ]),
        "",
        "  Por país:",
        *_tabla_satisfaccion("País", satisf["por_pais"]),
        "",
        "  Por categoría:",
        *_tabla_satisfaccion("Categoría", satisf["por_categoria"]),
        "",
        "  Por transportista:",
        *_tabla_satisfaccion("Transportista", satisf["por_transportista"]),
        "",
        "=" * ANCHO,
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Exportación y CLI
# ---------------------------------------------------------------------------

RESPUESTAS_SI = {"s", "si", "sí", "y", "yes"}
RESPUESTAS_NO = {"n", "no"}


def exportar_csv(resultado: dict, destino: str | Path) -> Path:
    """Escribe la exportación en disco (mismos bytes que devuelve la API)."""
    destino = Path(destino)
    destino.write_bytes(generar_csv_bytes(resultado))
    return destino


def preguntar_exportacion(leer: Callable[[str], str] | None = None) -> bool:
    """Pregunta si exportar. Repite ante respuestas no válidas; EOF o Ctrl+C = no."""
    leer = leer or input
    while True:
        try:
            respuesta = leer("¿Deseas exportar los resultados a CSV? [s / n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if respuesta in RESPUESTAS_SI:
            return True
        if respuesta in RESPUESTAS_NO:
            return False
        print("Respuesta no válida. Escribe 's' para exportar o 'n' para salir.")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Analiza el CSV de incidencias de TrackFlow.")
    parser.add_argument("csv", help="ruta al fichero CSV de incidencias")
    parser.add_argument("-o", "--output", default="results.csv", help="fichero de exportación (por defecto: results.csv)")
    args = parser.parse_args(argv)

    try:
        filas = leer_csv(args.csv)
    except ErrorAnalisis as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        resultado = analizar(filas, Path(args.csv).name)
        informe = formatear_informe(resultado)
    except Exception as error:  # noqa: BLE001 - red final de la CLI: un fallo imprevisto no debe acabar en una traza
        # Solo el tipo: el mensaje de un error imprevisto podría arrastrar datos de una fila (p. ej. un correo).
        print(f"Error: no se pudo completar el análisis ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(informe)

    if not preguntar_exportacion():
        print("No se ha exportado ningún fichero.")
        return 0
    try:
        destino = exportar_csv(resultado, args.output)
    except OSError as error:
        # `strerror` puede faltar (p. ej. en un `OSError` creado sin código de error).
        motivo = error.strerror or type(error).__name__
        print(f"Error: no se pudo escribir la exportación: {motivo}", file=sys.stderr)
        return 1
    print(f"Resultados exportados a {destino.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
