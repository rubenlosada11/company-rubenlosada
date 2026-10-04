"""Lectura del CSV y comprobación de su estructura."""

import csv
import io
from pathlib import Path
from typing import NamedTuple

from .dominio import CAMPOS


class ErrorAnalisis(Exception):
    """Error que impide analizar el fichero completo (no un registro concreto)."""


class Fila(NamedTuple):
    linea: int
    datos: dict[str, str]
    columnas_ok: bool


def leer_csv(ruta: str | Path) -> list[Fila]:
    """Lee un CSV desde disco y lo convierte en filas."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAnalisis(f"El fichero no existe: {ruta}")
    if not ruta.is_file():
        raise ErrorAnalisis(f"La ruta no es un fichero: {ruta}")
    try:
        contenido = ruta.read_bytes()
    except OSError as error:
        raise ErrorAnalisis(f"No se puede leer el fichero: {error.strerror or type(error).__name__}") from None
    return decodificar_csv(contenido)


def decodificar_csv(contenido: bytes) -> list[Fila]:
    """Convierte los bytes de un CSV (UTF-8, con o sin BOM) en filas."""
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErrorAnalisis("El fichero no está codificado en UTF-8.") from None
    return parsear_csv(texto)


def parsear_csv(texto: str) -> list[Fila]:
    """Convierte el contenido de un CSV en filas, comprobando su estructura."""
    if not texto.strip():
        raise ErrorAnalisis("El fichero está vacío.")

    lector = csv.reader(io.StringIO(texto))
    try:
        cabecera = [nombre.strip() for nombre in next(lector)]
        faltan = [campo for campo in CAMPOS if campo not in cabecera]
        if faltan:
            raise ErrorAnalisis(f"Faltan columnas obligatorias: {', '.join(faltan)}")

        filas = []
        for valores in lector:
            if not any(valor.strip() for valor in valores):
                continue  # línea en blanco: no es un registro
            datos = {
                campo: valores[i].strip() if i < len(valores) else ""
                for i, campo in enumerate(cabecera)
            }
            filas.append(Fila(lector.line_num, datos, len(valores) == len(cabecera)))
    except csv.Error:
        # El texto de `csv.Error` es interno y está en inglés («field larger than field limit…»): solo se indica dónde.
        raise ErrorAnalisis(f"El CSV está mal formado (cerca de la línea {lector.line_num}).") from None

    if not filas:
        raise ErrorAnalisis("El fichero no contiene registros (solo cabecera).")
    return filas
