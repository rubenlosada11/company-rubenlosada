"""Respuesta de `POST /api/incidents/analyze` (analizador de incidencias). Contexto: CONTEXT-incidencias.es.md.

`analizar()` (paquete `analisis-incidencias`) devuelve un `dict`; este esquema es el contrato público de la API y
reproduce la forma que consume el backoffice (`uis/backoffice/types/incidencias.ts`). Cualquier clave que el paquete
añadiera en el futuro se descarta (`extra="ignore"`, comportamiento por defecto) hasta declararla aquí: así un dato
del CSV como `customer_email` no puede llegar al cliente sin una decisión explícita.

Los nombres de campo van en español porque son los del paquete y los del frontend.
"""

from pydantic import BaseModel

Conteo = dict[str, int]
"""Valor → número de registros. Las claves son los valores del CONTEXT (categorías, estados, países…)."""


class Totales(BaseModel):
    procesados: int
    validos: int
    invalidos: int


class RegistroInvalido(BaseModel):
    """Fila rechazada: número de línea del CSV, ID de la incidencia (puede venir vacío) y reglas que incumple."""

    linea: int
    incident_id: str
    reglas: list[str]


class PorFecha(BaseModel):
    mes: Conteo
    trimestre: Conteo
    semana: Conteo
    dia_semana: Conteo


class Cruces(BaseModel):
    pais_categoria: dict[str, Conteo]
    transportista_categoria: dict[str, Conteo]
    transportista_estado: dict[str, Conteo]


class Satisfaccion(BaseModel):
    cerradas: int
    con_puntuacion: int
    media: float | None
    distribucion: Conteo


class SatisfaccionGlobal(Satisfaccion):
    por_pais: dict[str, Satisfaccion]
    por_categoria: dict[str, Satisfaccion]
    por_transportista: dict[str, Satisfaccion]


class Regla(BaseModel):
    """Etiqueta legible de una regla de validación, para que el frontend no la duplique."""

    etiqueta: str
    complementaria: bool


class ResultadoAnalisis(BaseModel):
    """Resumen de métricas del CSV. Sin datos personales: ni correos ni descripciones de las incidencias."""

    archivo: str
    totales: Totales
    invalidos_por_regla: Conteo
    registros_invalidos: list[RegistroInvalido]
    por_categoria: Conteo
    por_estado: Conteo
    por_pais: Conteo
    por_tipo_cliente: Conteo
    por_transportista: Conteo
    por_fecha: PorFecha
    cruces: Cruces
    satisfaccion: SatisfaccionGlobal
    reglas: dict[str, Regla]
