"""Validación de registros según las reglas de CONTEXT-incidencias.es.md."""

import re
from datetime import date, datetime

from .dominio import (
    CATEGORIAS,
    ESTADO_CERRADO,
    ESTADOS,
    LONGITUD_MIN_DESCRIPCION,
    LONGITUD_MIN_TRACKING,
    PAISES,
    PATRON_FECHA,
    PATRON_ID,
    PUNTUACION_MAX,
    PUNTUACION_MIN,
    REGLAS,
    TIPOS_CLIENTE,
    TRANSPORTISTAS,
    TRANSPORTISTAS_POR_PAIS,
)


def parsear_puntuacion(valor: str) -> int | None:
    """Devuelve la puntuación si es un entero entre 1 y 5; si no, None."""
    if not re.fullmatch(r"\d+", valor):
        return None
    puntuacion = int(valor)
    return puntuacion if PUNTUACION_MIN <= puntuacion <= PUNTUACION_MAX else None


def parsear_fecha(valor: str) -> date | None:
    """Devuelve la fecha si tiene formato YYYY-MM-DD y existe; si no, None."""
    if not PATRON_FECHA.fullmatch(valor):
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def validar_registro(datos: dict[str, str], columnas_ok: bool = True) -> list[str]:
    """Devuelve los códigos de las reglas que incumple el registro ([] si es válido)."""
    errores = set()

    pais = datos.get("country", "")
    carrier = datos.get("carrier", "")
    if pais not in PAISES:
        errores.add("pais_invalido")
        # Sin país válido solo se comprueba que el carrier exista, para no
        # contar dos veces el mismo problema.
        if carrier not in TRANSPORTISTAS:
            errores.add("transportista_invalido")
    elif carrier not in TRANSPORTISTAS_POR_PAIS[pais]:
        errores.add("transportista_invalido")

    if len(datos.get("tracking_number", "")) < LONGITUD_MIN_TRACKING:
        errores.add("tracking_invalido")
    if datos.get("category", "") not in CATEGORIAS:
        errores.add("categoria_invalida")
    if len(datos.get("description", "")) < LONGITUD_MIN_DESCRIPCION:
        errores.add("descripcion_invalida")
    if "@" not in datos.get("customer_email", ""):
        errores.add("email_invalido")

    estado = datos.get("status", "")
    puntuacion = datos.get("satisfaction_score", "")
    if estado == ESTADO_CERRADO and not puntuacion:
        errores.add("cerrada_sin_puntuacion")
    if puntuacion and parsear_puntuacion(puntuacion) is None:
        errores.add("puntuacion_fuera_rango")

    if not PATRON_ID.fullmatch(datos.get("incident_id", "")):
        errores.add("id_invalido")
    if parsear_fecha(datos.get("date", "")) is None:
        errores.add("fecha_invalida")
    if datos.get("customer_type", "") not in TIPOS_CLIENTE:
        errores.add("tipo_cliente_invalido")
    if estado not in ESTADOS:
        errores.add("estado_invalido")
    if not columnas_ok:
        errores.add("fila_mal_formada")

    return [codigo for codigo in REGLAS if codigo in errores]
