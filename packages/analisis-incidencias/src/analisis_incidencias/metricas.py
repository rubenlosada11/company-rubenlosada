"""Cálculo de métricas sobre los registros válidos."""

from collections import Counter
from typing import Callable

from .carga import Fila
from .dominio import (
    CATEGORIAS,
    DIAS_SEMANA,
    ESTADO_CERRADO,
    ESTADOS,
    PAISES,
    PUNTUACIONES,
    REGLAS,
    TIPOS_CLIENTE,
    TRANSPORTISTAS,
)
from .validacion import parsear_fecha, validar_registro


def porcentaje(parte: int, total: int) -> float | None:
    return round(parte * 100 / total, 1) if total else None


def _contar(registros: list[dict], campo: str, orden: tuple[str, ...]) -> dict[str, int]:
    conteo = Counter(r[campo] for r in registros)
    return {valor: conteo[valor] for valor in orden}


def _contar_por(registros: list[dict], clave: Callable[[dict], str]) -> dict[str, int]:
    conteo = Counter(clave(r) for r in registros)
    return dict(sorted(conteo.items()))


def _cruce(
    registros: list[dict], campo_fila: str, filas: tuple[str, ...], campo_col: str, columnas: tuple[str, ...]
) -> dict[str, dict[str, int]]:
    conteo = Counter((r[campo_fila], r[campo_col]) for r in registros)
    return {f: {c: conteo[(f, c)] for c in columnas} for f in filas}


def _satisfaccion(registros: list[dict]) -> dict:
    cerradas = [r for r in registros if r["status"] == ESTADO_CERRADO]
    puntuaciones = [int(r["satisfaction_score"]) for r in cerradas if r["satisfaction_score"]]
    conteo = Counter(puntuaciones)
    return {
        "cerradas": len(cerradas),
        "con_puntuacion": len(puntuaciones),
        "media": round(sum(puntuaciones) / len(puntuaciones), 2) if puntuaciones else None,
        "distribucion": {str(p): conteo[p] for p in PUNTUACIONES},
    }


def _satisfaccion_por(registros: list[dict], campo: str, orden: tuple[str, ...]) -> dict[str, dict]:
    return {valor: _satisfaccion([r for r in registros if r[campo] == valor]) for valor in orden}


def _clave_mes(r: dict) -> str:
    d = parsear_fecha(r["date"])
    return f"{d.year}-{d.month:02d}"


def _clave_trimestre(r: dict) -> str:
    d = parsear_fecha(r["date"])
    return f"{d.year}-T{(d.month - 1) // 3 + 1}"


def _clave_semana(r: dict) -> str:
    anio, semana, _ = parsear_fecha(r["date"]).isocalendar()
    return f"{anio}-S{semana:02d}"


def analizar(filas: list[Fila], archivo: str) -> dict:
    """Valida las filas y calcula todas las métricas sobre los registros válidos.

    Devuelve un diccionario serializable a JSON. No incluye datos personales.
    """
    validos: list[dict] = []
    registros_invalidos = []
    for fila in filas:
        reglas = validar_registro(fila.datos, fila.columnas_ok)
        if reglas:
            registros_invalidos.append(
                {"linea": fila.linea, "incident_id": fila.datos.get("incident_id", ""), "reglas": reglas}
            )
        else:
            validos.append(fila.datos)

    conteo_reglas = Counter(regla for r in registros_invalidos for regla in r["reglas"])
    dias = Counter(DIAS_SEMANA[parsear_fecha(r["date"]).weekday()] for r in validos)

    return {
        "archivo": archivo,
        "totales": {
            "procesados": len(filas),
            "validos": len(validos),
            "invalidos": len(registros_invalidos),
        },
        "invalidos_por_regla": {codigo: conteo_reglas[codigo] for codigo in REGLAS},
        "registros_invalidos": registros_invalidos,
        "por_categoria": _contar(validos, "category", CATEGORIAS),
        "por_estado": _contar(validos, "status", ESTADOS),
        "por_pais": _contar(validos, "country", PAISES),
        "por_tipo_cliente": _contar(validos, "customer_type", TIPOS_CLIENTE),
        "por_transportista": _contar(validos, "carrier", TRANSPORTISTAS),
        "por_fecha": {
            "mes": _contar_por(validos, _clave_mes),
            "trimestre": _contar_por(validos, _clave_trimestre),
            "semana": _contar_por(validos, _clave_semana),
            "dia_semana": {dia: dias[dia] for dia in DIAS_SEMANA},
        },
        "cruces": {
            "pais_categoria": _cruce(validos, "country", PAISES, "category", CATEGORIAS),
            "transportista_categoria": _cruce(validos, "carrier", TRANSPORTISTAS, "category", CATEGORIAS),
            "transportista_estado": _cruce(validos, "carrier", TRANSPORTISTAS, "status", ESTADOS),
        },
        "satisfaccion": {
            **_satisfaccion(validos),
            "por_pais": _satisfaccion_por(validos, "country", PAISES),
            "por_categoria": _satisfaccion_por(validos, "category", CATEGORIAS),
            "por_transportista": _satisfaccion_por(validos, "carrier", TRANSPORTISTAS),
        },
    }
