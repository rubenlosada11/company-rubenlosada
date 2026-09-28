"""Exportación del resultado a CSV: una fila por métrica."""

import csv
import io

from .metricas import porcentaje

CABECERA_EXPORTACION = ("seccion", "metrica", "valor", "porcentaje")
# UTF-8 con BOM para que Excel respete los acentos (p. ej. "miércoles").
CODIFICACION_EXPORTACION = "utf-8-sig"


def filas_exportacion(resultado: dict) -> list[tuple]:
    """Una fila por métrica. El porcentaje es sobre el total de su grupo:
    registros válidos en los desgloses simples, la fila (país o transportista)
    en los cruces y las incidencias puntuadas en la distribución de satisfacción.
    """
    totales = resultado["totales"]
    validos = totales["validos"]
    filas: list[tuple] = []

    def simple(seccion: str, conteo: dict[str, int], total: int | None) -> None:
        for clave, n in conteo.items():
            pct = porcentaje(n, total) if total is not None else None
            filas.append((seccion, clave, n, "" if pct is None else pct))

    simple("resumen", {
        "registros_procesados": totales["procesados"],
        "registros_validos": validos,
        "registros_invalidos": totales["invalidos"],
    }, None)
    simple("invalidos", resultado["invalidos_por_regla"], None)
    simple("categoria", resultado["por_categoria"], validos)
    simple("estado", resultado["por_estado"], validos)
    simple("pais", resultado["por_pais"], validos)
    simple("tipo_cliente", resultado["por_tipo_cliente"], validos)
    simple("transportista", resultado["por_transportista"], validos)
    for periodo, conteo in resultado["por_fecha"].items():
        simple(periodo, conteo, validos)
    for nombre, cruce in resultado["cruces"].items():
        for fila, conteo in cruce.items():
            total_fila = sum(conteo.values())
            simple(nombre, {f"{fila}|{col}": n for col, n in conteo.items()}, total_fila)

    satisf = resultado["satisfaccion"]
    simple("satisfaccion", {"cerradas": satisf["cerradas"], "con_puntuacion": satisf["con_puntuacion"]}, None)
    filas.append(("satisfaccion", "media", "" if satisf["media"] is None else satisf["media"], ""))
    simple("satisfaccion", {f"puntuacion_{p}": n for p, n in satisf["distribucion"].items()}, satisf["con_puntuacion"])
    for grupo in ("por_pais", "por_categoria", "por_transportista"):
        seccion = f"satisfaccion_{grupo.removeprefix('por_')}"
        for clave, s in satisf[grupo].items():
            filas.append((seccion, f"{clave}|con_puntuacion", s["con_puntuacion"], ""))
            filas.append((seccion, f"{clave}|media", "" if s["media"] is None else s["media"], ""))
    return filas


def generar_csv(resultado: dict) -> str:
    """Devuelve la exportación como texto CSV."""
    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(CABECERA_EXPORTACION)
    escritor.writerows(filas_exportacion(resultado))
    return salida.getvalue()


def generar_csv_bytes(resultado: dict) -> bytes:
    """Exportación lista para escribir en disco o enviar por HTTP (mismos bytes en ambos casos)."""
    return generar_csv(resultado).encode(CODIFICACION_EXPORTACION)
