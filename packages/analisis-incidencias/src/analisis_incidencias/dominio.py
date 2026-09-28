"""Constantes del dominio de incidencias de TrackFlow (fuente: CONTEXT-incidencias.es.md)."""

import re

CAMPOS = (
    "incident_id",
    "date",
    "country",
    "customer_type",
    "tracking_number",
    "carrier",
    "category",
    "description",
    "status",
    "customer_email",
    "satisfaction_score",
)

PAISES = ("US", "ES")
TRANSPORTISTAS_POR_PAIS = {
    "US": ("UPS", "FEDEX", "DHL_US"),
    "ES": ("MRW", "SEUR", "DHL_ES", "LOCAL_ES"),
}
TRANSPORTISTAS = tuple(t for pais in PAISES for t in TRANSPORTISTAS_POR_PAIS[pais])
CATEGORIAS = ("LOST_PARCEL", "DELAYED_DELIVERY", "WRONG_ADDRESS", "RETURN_REQUEST", "DAMAGE")
ESTADOS = ("OPEN", "CLOSED", "DISCARDED")
TIPOS_CLIENTE = ("B2B", "B2C")

ESTADO_CERRADO = "CLOSED"
PUNTUACION_MIN, PUNTUACION_MAX = 1, 5
PUNTUACIONES = tuple(range(PUNTUACION_MIN, PUNTUACION_MAX + 1))
ETIQUETAS_PUNTUACION = {
    1: "Muy insatisfecho",
    2: "Insatisfecho",
    3: "Neutral",
    4: "Satisfecho",
    5: "Muy satisfecho",
}
LONGITUD_MIN_TRACKING = 8
LONGITUD_MIN_DESCRIPCION = 5
PATRON_ID = re.compile(r"TRF-\d{6}")
PATRON_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")

DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# Reglas de invalidez definidas explícitamente en CONTEXT-incidencias.es.md.
REGLAS_CONTEXT = {
    "pais_invalido": "País ausente o inválido",
    "transportista_invalido": "Transportista inválido para el país",
    "tracking_invalido": "Número de seguimiento inválido",
    "categoria_invalida": "Categoría ausente o inválida",
    "descripcion_invalida": "Descripción ausente o muy corta",
    "email_invalido": "Email ausente o inválido",
    "cerrada_sin_puntuacion": "Cerrada sin puntuación",
    "puntuacion_fuera_rango": "Puntuación fuera de rango",
}
# Reglas complementarias: derivan de la tabla de campos obligatorios del
# CONTEXT (formato y valores permitidos), no de su lista de reglas.
REGLAS_COMPLEMENTARIAS = {
    "id_invalido": "ID de incidencia inválido",
    "fecha_invalida": "Fecha ausente o inválida",
    "tipo_cliente_invalido": "Tipo de cliente inválido",
    "estado_invalido": "Estado ausente o inválido",
    "fila_mal_formada": "Número de columnas incorrecto",
}
REGLAS = {**REGLAS_CONTEXT, **REGLAS_COMPLEMENTARIAS}
