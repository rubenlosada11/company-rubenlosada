"""Análisis de incidencias de TrackFlow: carga, validación, métricas y exportación.

Lógica compartida por el script `scripts/analyze.py` y la API `services/api`.
Solo usa la biblioteca estándar y procesa los datos en local.
"""

from .carga import ErrorAnalisis, Fila, decodificar_csv, leer_csv, parsear_csv
from .dominio import REGLAS, REGLAS_COMPLEMENTARIAS, REGLAS_CONTEXT
from .exportacion import CABECERA_EXPORTACION, filas_exportacion, generar_csv, generar_csv_bytes
from .metricas import analizar, porcentaje
from .validacion import parsear_fecha, parsear_puntuacion, validar_registro

__all__ = [
    "CABECERA_EXPORTACION",
    "REGLAS",
    "REGLAS_COMPLEMENTARIAS",
    "REGLAS_CONTEXT",
    "ErrorAnalisis",
    "Fila",
    "analizar",
    "decodificar_csv",
    "filas_exportacion",
    "generar_csv",
    "generar_csv_bytes",
    "leer_csv",
    "parsear_csv",
    "parsear_fecha",
    "parsear_puntuacion",
    "porcentaje",
    "validar_registro",
]
