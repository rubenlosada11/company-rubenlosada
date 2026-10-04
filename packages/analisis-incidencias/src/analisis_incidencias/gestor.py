"""Dominio y validación del gestor de incidencias (fuente: CONTEXT-gestor-incidencias.es.md).

Lógica compartida por el seed (`scripts/seed_incidents.py`) y la API (`services/api`). Solo biblioteca estándar.
Los nombres de campo y los valores son los del modelo `Incident`, que no coinciden con los del CSV del analizador
(`dominio.py`).
"""

from datetime import UTC, datetime

from .validacion import parsear_fecha

# Valor en base de datos → nombre para mostrar (tabla «Almacenes y oficinas» del CONTEXT).
SEDES = {
    "central": "Central",
    "la_warehouse": "Los Ángeles — Almacén",
    "la_office": "Los Ángeles — Oficina",
    "zaragoza_warehouse": "Zaragoza — Almacén",
    "zaragoza_office": "Zaragoza — Oficina",
}
CATEGORIAS = (
    "lost_parcel",
    "delivery_failure",
    "inventory_discrepancy",
    "carrier_issue",
    "returns_issue",
    "warehouse_incident",
    "system_failure",
    "client_complaint",
    "other",
)
ESTADOS = ("open", "in_progress", "resolved", "discarded")
ORIGENES = ("customer", "branch", "internal")

ESTADO_INICIAL = "open"
# Estado actual → estados a los que puede pasar. `resolved` y `discarded` son finales.
TRANSICIONES = {
    "open": ("in_progress", "discarded"),
    "in_progress": ("resolved", "discarded"),
    "resolved": (),
    "discarded": (),
}

# El CONTEXT fija 120 caracteres para el título del seed. El máximo de la descripción es un límite técnico.
LONGITUD_MAX_TITULO = 120
LONGITUD_MAX_DESCRIPCION = 2000

CAMPOS_TEXTO = {"title": LONGITUD_MAX_TITULO, "description": LONGITUD_MAX_DESCRIPCION}
CAMPOS_VALOR = {
    "category": CATEGORIAS,
    "status": ESTADOS,
    "origin": ORIGENES,
    "branch": tuple(SEDES),
}
# Todos son obligatorios, también `description` y `branch`.
CAMPOS = (*CAMPOS_TEXTO, *CAMPOS_VALOR)

OBLIGATORIO = {
    "title": "El título es obligatorio.",
    "description": "La descripción es obligatoria.",
    "category": "La categoría es obligatoria.",
    "status": "El estado es obligatorio.",
    "origin": "El origen es obligatorio.",
    "branch": "La sede es obligatoria.",
}
NO_VALIDO = {
    "category": "La categoría no es válida.",
    "status": "El estado no es válido.",
    "origin": "El origen no es válido.",
    "branch": "La sede no es válida.",
}
ETIQUETAS = {
    "title": "El título",
    "description": "La descripción",
    "category": "La categoría",
    "status": "El estado",
    "origin": "El origen",
    "branch": "La sede",
}


def validar_campo(campo: str, valor: object) -> str | None:
    """Devuelve el mensaje de error del campo, o None si el valor es válido."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return OBLIGATORIO[campo]
    if not isinstance(valor, str):
        return f"{ETIQUETAS[campo]} debe ser un texto."

    valor = valor.strip()
    if campo in CAMPOS_TEXTO:
        maximo = CAMPOS_TEXTO[campo]
        if len(valor) > maximo:
            return f"{ETIQUETAS[campo]} no puede superar los {maximo} caracteres."
        return None

    admitidos = CAMPOS_VALOR[campo]
    if valor not in admitidos:
        return f"{NO_VALIDO[campo]} Valores admitidos: {', '.join(admitidos)}."
    return None


def validar_incidencia(datos: dict, campos: tuple[str, ...] = CAMPOS) -> dict[str, str]:
    """Devuelve `{campo: mensaje}` con los campos que no son válidos ({} si la incidencia es válida)."""
    errores = {}
    for campo in campos:
        mensaje = validar_campo(campo, datos.get(campo))
        if mensaje:
            errores[campo] = mensaje
    return errores


def transicion_permitida(actual: str, nuevo: str) -> bool:
    """Indica si una incidencia en estado `actual` puede pasar a `nuevo`."""
    return nuevo in TRANSICIONES.get(actual, ())


def validar_transicion(actual: str, nuevo: str) -> str | None:
    """Devuelve por qué no se puede pasar de `actual` a `nuevo`, o None si la transición está permitida."""
    if transicion_permitida(actual, nuevo):
        return None
    permitidos = TRANSICIONES.get(actual, ())
    if not permitidos:
        return f"La incidencia está en un estado final ({actual}) y ya no admite cambios de estado."
    if nuevo == actual:
        return f"La incidencia ya está en estado {actual}."
    return f"No se puede pasar de {actual} a {nuevo}. Desde {actual} solo se admite: {', '.join(permitidos)}."


# --- CSV histórico del analizador → modelo (sección «Datos históricos — seed desde CSV» del CONTEXT) -------------

MAPEO_ESTADOS = {"OPEN": "open", "CLOSED": "resolved", "DISCARDED": "discarded"}
MAPEO_CATEGORIAS = {
    "LOST_PARCEL": "lost_parcel",
    "DELAYED_DELIVERY": "carrier_issue",
    "WRONG_ADDRESS": "delivery_failure",
    "RETURN_REQUEST": "returns_issue",
    "DAMAGE": "carrier_issue",
}
MAPEO_SEDES = {"US": "la_office", "ES": "zaragoza_office"}
# Todo el CSV son incidencias comunicadas por clientes o consumidores finales.
ORIGEN_CSV = "customer"

_MAPEOS = (
    ("status", "status", MAPEO_ESTADOS, "Estado"),
    ("category", "category", MAPEO_CATEGORIAS, "Categoría"),
    ("country", "branch", MAPEO_SEDES, "País"),
)


class ErrorTransformacion(ValueError):
    """La fila del CSV no se puede convertir en una incidencia del gestor."""


def transformar_fila(datos: dict[str, str]) -> dict:
    """Convierte una fila del CSV del analizador en los datos de una incidencia del gestor.

    Devuelve los campos del modelo más `source_id` (el `incident_id` del CSV, solo para no duplicar). No valida la
    fila como incidencia del analizador: eso lo hace antes `validar_registro`.
    """
    descripcion = datos.get("description", "")
    titulo = descripcion[:LONGITUD_MAX_TITULO].strip()
    if not titulo:
        raise ErrorTransformacion("Descripción vacía: no se puede obtener el título")

    fecha = parsear_fecha(datos.get("date", ""))
    if fecha is None:
        raise ErrorTransformacion(f"Fecha no válida: '{datos.get('date', '')}'")
    creada = datetime(fecha.year, fecha.month, fecha.day, tzinfo=UTC)  # medianoche UTC

    incidencia = {
        "source_id": datos.get("incident_id", ""),
        "title": titulo,
        "description": descripcion,
        "origin": ORIGEN_CSV,
        "created_at": creada,
        "updated_at": creada,
    }
    for campo_csv, campo, mapeo, nombre in _MAPEOS:
        valor = datos.get(campo_csv, "")
        if valor not in mapeo:
            raise ErrorTransformacion(f"{nombre} sin equivalencia en el gestor: '{valor}'")
        incidencia[campo] = mapeo[valor]
    return incidencia
