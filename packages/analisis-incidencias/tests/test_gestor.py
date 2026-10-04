"""Tests de la validación compartida del gestor de incidencias."""

import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from analisis_incidencias import gestor, leer_csv, validar_registro
from analisis_incidencias.dominio import CATEGORIAS as CATEGORIAS_CSV
from analisis_incidencias.dominio import ESTADOS as ESTADOS_CSV
from analisis_incidencias.dominio import PAISES

CONTEXT = Path(__file__).resolve().parents[3] / "CONTEXT-gestor-incidencias.es.md"

INCIDENCIA_VALIDA = {
    "title": "Paquete no localizado en el muelle 3",
    "description": "El paquete figura como recibido pero no aparece en la ubicación asignada.",
    "category": "lost_parcel",
    "status": "open",
    "origin": "branch",
    "branch": "zaragoza_warehouse",
}


def incidencia(**cambios):
    return {**INCIDENCIA_VALIDA, **cambios}


def seccion(titulo: str) -> str:
    """Texto del CONTEXT entre un encabezado `## titulo` y el siguiente."""
    texto = CONTEXT.read_text(encoding="utf-8")
    return re.split(r"^## ", texto.split(f"## {titulo}", 1)[1], maxsplit=1, flags=re.MULTILINE)[0]


def primera_columna(titulo: str) -> list[str]:
    return re.findall(r"^\| `([a-z_]+)`", seccion(titulo), flags=re.MULTILINE)


# --- Los valores son exactamente los del CONTEXT ---------------------------------------------------------------


def test_sedes_y_etiquetas_son_las_del_context():
    filas = re.findall(r"^\| `([a-z_]+)`\s*\| (.+?)\s*\|$", seccion("Almacenes y oficinas"), flags=re.MULTILINE)
    assert dict(filas) == gestor.SEDES
    assert gestor.SEDES["central"] == "Central"


def test_categorias_estados_y_origenes_son_los_del_context():
    assert primera_columna("Categorías de incidencias") == list(gestor.CATEGORIAS)
    assert primera_columna("Estados y ciclo de vida") == list(gestor.ESTADOS)
    assert primera_columna("Orígenes") == list(gestor.ORIGENES)


def test_transiciones_son_las_del_context():
    frase = seccion("Estados y ciclo de vida")
    pares = set(re.findall(r"`(\w+) → (\w+)`", frase))
    assert pares == {(actual, nuevo) for actual, nuevos in gestor.TRANSICIONES.items() for nuevo in nuevos}
    assert set(gestor.TRANSICIONES) == set(gestor.ESTADOS)


# --- Validación ------------------------------------------------------------------------------------------------


def test_incidencia_valida():
    assert gestor.validar_incidencia(INCIDENCIA_VALIDA) == {}


@pytest.mark.parametrize("campo", gestor.CAMPOS)
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_todos_los_campos_son_obligatorios(campo, valor):
    errores = gestor.validar_incidencia(incidencia(**{campo: valor}))
    assert errores == {campo: gestor.OBLIGATORIO[campo]}


@pytest.mark.parametrize("campo", gestor.CAMPOS)
def test_campo_ausente(campo):
    datos = {clave: valor for clave, valor in INCIDENCIA_VALIDA.items() if clave != campo}
    assert list(gestor.validar_incidencia(datos)) == [campo]


def test_la_descripcion_es_obligatoria():
    assert gestor.validar_campo("description", "") == "La descripción es obligatoria."
    assert "description" in gestor.CAMPOS


def test_la_sede_es_obligatoria_con_cualquier_origen():
    for origen in gestor.ORIGENES:
        assert "branch" in gestor.validar_incidencia(incidencia(origin=origen, branch=""))


@pytest.mark.parametrize("campo", gestor.CAMPOS)
@pytest.mark.parametrize("valor", [123, 4.5, True, ["open"], {"a": 1}])
def test_tipo_incorrecto(campo, valor):
    assert gestor.validar_campo(campo, valor) == f"{gestor.ETIQUETAS[campo]} debe ser un texto."


def test_longitud_maxima_del_titulo():
    assert gestor.validar_campo("title", "a" * 120) is None
    assert gestor.validar_campo("title", "a" * 121) == "El título no puede superar los 120 caracteres."
    assert gestor.validar_campo("title", "  " + "a" * 120 + "  ") is None  # los espacios de los extremos no cuentan


def test_longitud_maxima_de_la_descripcion():
    assert gestor.validar_campo("description", "a" * 2000) is None
    assert gestor.validar_campo("description", "a" * 2001) == "La descripción no puede superar los 2000 caracteres."


@pytest.mark.parametrize(
    ("campo", "validos"),
    [
        ("category", gestor.CATEGORIAS),
        ("status", gestor.ESTADOS),
        ("origin", gestor.ORIGENES),
        ("branch", tuple(gestor.SEDES)),
    ],
)
def test_valores_admitidos(campo, validos):
    for valor in validos:
        assert gestor.validar_campo(campo, valor) is None
    mensaje = gestor.validar_campo(campo, "no_existe")
    assert mensaje.startswith(gestor.NO_VALIDO[campo])
    assert all(valor in mensaje for valor in validos)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("category", "LOST_PARCEL"),  # los códigos del CSV del analizador no son valores del modelo
        ("status", "OPEN"),
        ("status", "CLOSED"),
        ("branch", "Central"),  # la etiqueta no es el valor
        ("branch", "US"),
        ("origin", "Customer"),
    ],
)
def test_valores_del_csv_o_etiquetas_no_son_validos(campo, valor):
    assert gestor.validar_campo(campo, valor) is not None


def test_varios_errores_a_la_vez():
    errores = gestor.validar_incidencia(incidencia(title="", category="x", branch=None))
    assert list(errores) == ["title", "category", "branch"]


def test_validar_solo_algunos_campos():
    assert gestor.validar_incidencia({"status": "resolved"}, campos=("status",)) == {}


# --- Transiciones ----------------------------------------------------------------------------------------------

PERMITIDAS = {("open", "in_progress"), ("open", "discarded"), ("in_progress", "resolved"), ("in_progress", "discarded")}


@pytest.mark.parametrize("actual", gestor.ESTADOS)
@pytest.mark.parametrize("nuevo", gestor.ESTADOS)
def test_transiciones(actual, nuevo):
    assert gestor.transicion_permitida(actual, nuevo) is ((actual, nuevo) in PERMITIDAS)


def test_estados_finales_y_desconocidos():
    assert gestor.TRANSICIONES["resolved"] == () and gestor.TRANSICIONES["discarded"] == ()
    assert not gestor.transicion_permitida("open", "cerrada")
    assert not gestor.transicion_permitida("cerrada", "open")
    assert gestor.ESTADO_INICIAL == "open"


# --- CSV histórico → modelo -------------------------------------------------------------------------------------

CSV_HISTORICO = Path(__file__).resolve().parents[3] / "scripts" / "incidents-trackflow.csv"

FILA_CSV = {
    "incident_id": "TRF-000001",
    "date": "2024-01-08",
    "country": "ES",
    "customer_type": "B2C",
    "tracking_number": "ES12345678",
    "carrier": "SEUR",
    "category": "DAMAGE",
    "description": "Caja aplastada en el reparto",
    "status": "CLOSED",
    "customer_email": "persona@example.com",
    "satisfaction_score": "4",
}


def fila_csv(**cambios):
    return {**FILA_CSV, **cambios}


def test_mapeos_son_los_del_context():
    texto = seccion("Datos históricos — seed desde CSV")

    def tabla(titulo):
        bloque = texto.split(f"### {titulo}", 1)[1].split("###", 1)[0]
        return dict(re.findall(r"^\| `(\w+)`\s*\| `(\w+)`\s*\|$", bloque, flags=re.MULTILINE))

    assert tabla("Mapeo de estados") == gestor.MAPEO_ESTADOS
    assert tabla("Mapeo de categorías") == gestor.MAPEO_CATEGORIAS
    assert tabla("Mapeo de sede") == gestor.MAPEO_SEDES
    assert gestor.ORIGEN_CSV == "customer"


def test_los_mapeos_cubren_todos_los_valores_del_analizador():
    assert set(gestor.MAPEO_ESTADOS) == set(ESTADOS_CSV)
    assert set(gestor.MAPEO_CATEGORIAS) == set(CATEGORIAS_CSV)
    assert set(gestor.MAPEO_SEDES) == set(PAISES)


def test_transformar_fila():
    assert gestor.transformar_fila(FILA_CSV) == {
        "source_id": "TRF-000001",
        "title": "Caja aplastada en el reparto",
        "description": "Caja aplastada en el reparto",
        "category": "carrier_issue",
        "status": "resolved",
        "origin": "customer",
        "branch": "zaragoza_office",
        "created_at": datetime(2024, 1, 8, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 8, tzinfo=UTC),
    }


def test_la_fila_transformada_es_una_incidencia_valida():
    assert gestor.validar_incidencia(gestor.transformar_fila(FILA_CSV)) == {}


def test_no_incluye_datos_del_cliente():
    incidencia_csv = gestor.transformar_fila(FILA_CSV)
    assert "customer_email" not in incidencia_csv
    assert "@" not in str(incidencia_csv)


def test_titulo_son_los_primeros_120_caracteres_recortados():
    larga = "a" * 119 + " " + "b" * 30
    incidencia_csv = gestor.transformar_fila(fila_csv(description=larga))
    assert incidencia_csv["title"] == "a" * 119  # el carácter 120 es un espacio: se recorta
    assert incidencia_csv["description"] == larga  # la descripción se copia literalmente


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        ({"description": ""}, "Descripción vacía"),
        ({"description": "   "}, "Descripción vacía"),
        ({"date": "08/01/2024"}, "Fecha no válida"),
        ({"date": "2024-02-30"}, "Fecha no válida"),
        ({"status": "closed"}, "Estado sin equivalencia"),
        ({"category": "OTRA"}, "Categoría sin equivalencia"),
        ({"country": "FR"}, "País sin equivalencia"),
    ],
)
def test_filas_que_no_se_pueden_transformar(cambio, mensaje):
    with pytest.raises(gestor.ErrorTransformacion, match=mensaje):
        gestor.transformar_fila(fila_csv(**cambio))


def test_csv_historico_produce_los_valores_esperados_del_context():
    filas = leer_csv(CSV_HISTORICO)
    validas = [f for f in filas if not validar_registro(f.datos, f.columnas_ok)]
    incidencias = [gestor.transformar_fila(f.datos) for f in validas]

    assert (len(filas), len(incidencias)) == (100, 95)
    assert all(gestor.validar_incidencia(i) == {} for i in incidencias)
    assert Counter(i["status"] for i in incidencias) == {"open": 29, "resolved": 52, "discarded": 14}
    assert Counter(i["category"] for i in incidencias) == {
        "lost_parcel": 14,
        "carrier_issue": 45,
        "delivery_failure": 19,
        "returns_issue": 17,
    }
    assert {i["origin"] for i in incidencias} == {"customer"}
    assert {i["branch"] for i in incidencias} == {"la_office", "zaragoza_office"}
    assert len({i["source_id"] for i in incidencias}) == 95


@pytest.mark.parametrize("actual", gestor.ESTADOS)
@pytest.mark.parametrize("nuevo", gestor.ESTADOS)
def test_validar_transicion_coincide_con_transicion_permitida(actual, nuevo):
    assert (gestor.validar_transicion(actual, nuevo) is None) is gestor.transicion_permitida(actual, nuevo)


def test_mensajes_de_transicion():
    assert gestor.validar_transicion("resolved", "open") == (
        "La incidencia está en un estado final (resolved) y ya no admite cambios de estado."
    )
    assert gestor.validar_transicion("discarded", "discarded").startswith("La incidencia está en un estado final")
    assert gestor.validar_transicion("open", "open") == "La incidencia ya está en estado open."
    assert gestor.validar_transicion("open", "resolved") == (
        "No se puede pasar de open a resolved. Desde open solo se admite: in_progress, discarded."
    )
    assert gestor.validar_transicion("in_progress", "open") == (
        "No se puede pasar de in_progress a open. Desde in_progress solo se admite: resolved, discarded."
    )
