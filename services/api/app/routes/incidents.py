"""Endpoints del analizador de incidencias (`/api/incidents`).

Toda la validación y el cálculo se delegan en el paquete compartido `analisis-incidencias`, el mismo que usa
`scripts/analyze.py`. Contexto: CONTEXT-incidencias.es.md.

Ambos requieren un usuario autenticado (Bearer JWT): el CSV contiene correos de clientes.
"""

import logging
from pathlib import PurePath

from analisis_incidencias import (
    REGLAS,
    REGLAS_COMPLEMENTARIAS,
    ErrorAnalisis,
    analizar,
    decodificar_csv,
    generar_csv_bytes,
)
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.dependencies import get_current_user

logger = logging.getLogger("trackflow.api.incidents")

# Rutas del enunciado del ejercicio (con prefijo /api, a diferencia de /suppliers).
router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"description": "Sin token o con un token no válido o caducado"}},
)

TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB: el CSV de un mes ocupa ~15 KB por cada 100 filas
NOMBRE_EXPORTACION = "results.csv"
ERROR_INTERNO = "Error interno del servidor."

# Etiquetas legibles de cada regla, para que el frontend no las duplique.
ETIQUETAS_REGLAS = {
    codigo: {"etiqueta": etiqueta, "complementaria": codigo in REGLAS_COMPLEMENTARIAS}
    for codigo, etiqueta in REGLAS.items()
}


@router.post("/analyze")
async def analizar_incidencias(
    request: Request,
    file: UploadFile | None = File(None, description="CSV de incidencias (UTF-8, separado por comas)"),
) -> dict:
    """Valida el CSV y devuelve el resumen de métricas. No incluye datos personales."""
    if file is None or not file.filename:
        raise HTTPException(400, "No se ha enviado ningún fichero. Adjunta un CSV en el campo 'file'.")

    nombre = PurePath(file.filename.replace("\\", "/")).name
    if not nombre.lower().endswith(".csv"):
        raise HTTPException(415, f"Formato no admitido: '{nombre}'. El fichero debe tener extensión .csv.")

    contenido = await file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(413, f"El fichero supera el tamaño máximo de {TAMANO_MAXIMO // (1024 * 1024)} MB.")

    try:
        resultado = analizar(decodificar_csv(contenido), nombre)
    except ErrorAnalisis as error:
        raise HTTPException(422, str(error)) from None
    except Exception:
        # Solo en este router: la traza queda en el log del servidor y al cliente le llega un mensaje genérico.
        logger.exception("Error inesperado al analizar '%s'", nombre)
        raise HTTPException(500, ERROR_INTERNO) from None

    # Solo se guarda un análisis correcto: uno fallido no sustituye al anterior.
    request.app.state.ultimo_analisis = resultado
    totales = resultado["totales"]
    logger.info(
        "Análisis de '%s': %d registros (%d válidos, %d inválidos)",
        nombre, totales["procesados"], totales["validos"], totales["invalidos"],
    )
    return {**resultado, "reglas": ETIQUETAS_REGLAS}


@router.get("/results/export")
def exportar_resultados(request: Request) -> Response:
    """Descarga el último análisis como CSV (una fila por métrica)."""
    resultado = request.app.state.ultimo_analisis
    if resultado is None:
        raise HTTPException(404, "Todavía no se ha analizado ningún fichero. Usa primero POST /api/incidents/analyze.")

    try:
        contenido = generar_csv_bytes(resultado)
    except Exception:
        logger.exception("Error inesperado al exportar el último análisis")
        raise HTTPException(500, ERROR_INTERNO) from None

    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{NOMBRE_EXPORTACION}"'},
    )
