"""Tests de los endpoints del analizador de incidencias (`/api/incidents`). Ejecutar desde services/api: uv run pytest"""

import logging
import sys
from pathlib import Path

import pytest

from app.main import app
from app.routes import incidents

RAIZ_REPO = Path(__file__).resolve().parents[3]
CSV_REAL = RAIZ_REPO / "scripts" / "incidents-trackflow.csv"
CABECERA = (
    "incident_id,date,country,customer_type,tracking_number,carrier,category,"
    "description,status,customer_email,satisfaction_score"
)
FILA_VALIDA = "TRF-000001,2024-01-15,ES,B2C,ES12345678,SEUR,DAMAGE,Caja aplastada,CLOSED,persona@example.com,4"

sys.path.insert(0, str(RAIZ_REPO / "scripts"))
import analyze  # noqa: E402  (CLI del script, para comprobar equivalencia)


@pytest.fixture(autouse=True)
def sin_analisis_previo():
    """La app es global: cada test empieza (y deja la app) sin ningún análisis en memoria."""
    app.state.ultimo_analisis = None
    yield
    app.state.ultimo_analisis = None


def subir(client, contenido: bytes, nombre="incidents.csv", tipo="text/csv"):
    return client.post("/api/incidents/analyze", files={"file": (nombre, contenido, tipo)})


# --- POST /api/incidents/analyze ------------------------------------------------


def test_health_sigue_en_su_ruta(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_analiza_csv_real_con_valores_del_context(client):
    respuesta = subir(client, CSV_REAL.read_bytes(), CSV_REAL.name)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/json; charset=utf-8"
    datos = respuesta.json()
    assert datos["archivo"] == "incidents-trackflow.csv"
    assert datos["totales"] == {"procesados": 100, "validos": 95, "invalidos": 5}
    assert datos["por_categoria"] == {
        "LOST_PARCEL": 14, "DELAYED_DELIVERY": 38, "WRONG_ADDRESS": 19, "RETURN_REQUEST": 17, "DAMAGE": 7,
    }
    assert datos["por_estado"] == {"OPEN": 29, "CLOSED": 52, "DISCARDED": 14}
    assert datos["satisfaccion"]["media"] == 3.06
    assert datos["satisfaccion"]["distribucion"] == {"1": 6, "2": 11, "3": 15, "4": 14, "5": 6}
    assert {k: v for k, v in datos["invalidos_por_regla"].items() if v} == {
        "transportista_invalido": 1, "tracking_invalido": 1, "categoria_invalida": 1,
        "email_invalido": 1, "cerrada_sin_puntuacion": 1,
    }
    assert [r["incident_id"] for r in datos["registros_invalidos"]] == [
        "TRF-000003", "TRF-000025", "TRF-000042", "TRF-000068", "TRF-000097",
    ]


def test_respuesta_equivale_al_script(client):
    datos = subir(client, CSV_REAL.read_bytes(), CSV_REAL.name).json()
    del datos["reglas"]
    assert datos == analyze.analizar(analyze.leer_csv(CSV_REAL), CSV_REAL.name)


def test_respuesta_incluye_etiquetas_de_reglas(client):
    reglas = subir(client, CSV_REAL.read_bytes()).json()["reglas"]
    assert reglas["email_invalido"] == {"etiqueta": "Email ausente o inválido", "complementaria": False}
    assert reglas["estado_invalido"]["complementaria"] is True


def test_respuesta_no_contiene_correos(client):
    assert "@" not in subir(client, CSV_REAL.read_bytes()).text


def test_log_del_analisis_sin_correos(client, caplog):
    with caplog.at_level(logging.INFO, logger="trackflow"):
        subir(client, CSV_REAL.read_bytes(), CSV_REAL.name)
    assert "Análisis de 'incidents-trackflow.csv': 100 registros (95 válidos, 5 inválidos)" in caplog.text
    assert "@" not in caplog.text


def test_acepta_content_type_de_excel_en_windows(client):
    respuesta = subir(client, CSV_REAL.read_bytes(), tipo="application/vnd.ms-excel")
    assert respuesta.status_code == 200


def test_nombre_con_ruta_se_limpia(client):
    respuesta = subir(client, CSV_REAL.read_bytes(), nombre="C:\\Users\\x\\incidents.csv")
    assert respuesta.json()["archivo"] == "incidents.csv"


# --- Errores -----------------------------------------------------------------------


def test_sin_fichero_devuelve_400(client):
    respuesta = client.post("/api/incidents/analyze")
    assert respuesta.status_code == 400
    assert "No se ha enviado ningún fichero" in respuesta.json()["detail"]


def test_campo_con_otro_nombre_devuelve_400(client):
    respuesta = client.post("/api/incidents/analyze", files={"otro": ("a.csv", b"x", "text/csv")})
    assert respuesta.status_code == 400


def test_extension_incorrecta_devuelve_415(client):
    respuesta = subir(client, b"hola", nombre="datos.xlsx")
    assert respuesta.status_code == 415
    assert ".csv" in respuesta.json()["detail"]


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        (b"", "vacío"),
        (CABECERA.encode() + b"\n", "no contiene registros"),
        (b"a,b\n1,2\n", "Faltan columnas obligatorias"),
        ((CABECERA + "\n" + FILA_VALIDA.replace("Caja", "Caña")).encode("latin-1"), "UTF-8"),
    ],
)
def test_contenido_no_procesable_devuelve_422(client, contenido, mensaje):
    respuesta = subir(client, contenido)
    assert respuesta.status_code == 422
    assert mensaje in respuesta.json()["detail"]


def test_fichero_demasiado_grande_devuelve_413(client, monkeypatch):
    monkeypatch.setattr(incidents, "TAMANO_MAXIMO", 100)
    respuesta = subir(client, CSV_REAL.read_bytes())
    assert respuesta.status_code == 413


def test_error_inesperado_devuelve_500_sin_traza(client, monkeypatch, caplog):
    def fallar(*_args):
        raise RuntimeError("detalle interno")

    monkeypatch.setattr(incidents, "analizar", fallar)
    with caplog.at_level(logging.ERROR, logger="trackflow"):
        respuesta = subir(client, CSV_REAL.read_bytes())
    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "Error interno del servidor."}
    assert "detalle interno" in caplog.text  # la traza queda en el log del servidor
    assert app.state.ultimo_analisis is None


def test_error_inesperado_al_exportar_devuelve_500(client, monkeypatch):
    subir(client, CSV_REAL.read_bytes())
    monkeypatch.setattr(incidents, "generar_csv_bytes", lambda _resultado: 1 / 0)
    respuesta = client.get("/api/incidents/results/export")
    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "Error interno del servidor."}


# --- GET /api/incidents/results/export ----------------------------------------------


def test_exportar_sin_analisis_previo_devuelve_404(client):
    respuesta = client.get("/api/incidents/results/export")
    assert respuesta.status_code == 404
    assert "Todavía no se ha analizado" in respuesta.json()["detail"]


def test_exportar_devuelve_csv_descargable(client):
    subir(client, CSV_REAL.read_bytes(), CSV_REAL.name)
    respuesta = client.get("/api/incidents/results/export")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "text/csv; charset=utf-8"
    assert respuesta.headers["content-disposition"] == 'attachment; filename="results.csv"'
    texto = respuesta.content.decode("utf-8-sig")
    assert texto.startswith("seccion,metrica,valor,porcentaje\n")
    assert "categoria,DELAYED_DELIVERY,38,40.0" in texto
    assert "satisfaccion,media,3.06," in texto
    assert "@" not in texto


def test_exportacion_identica_a_la_del_script(client, tmp_path, monkeypatch):
    subir(client, CSV_REAL.read_bytes(), CSV_REAL.name)
    monkeypatch.setattr("builtins.input", lambda _prompt: "s")
    destino = tmp_path / "results.csv"
    assert analyze.main([str(CSV_REAL), "--output", str(destino)]) == 0
    assert client.get("/api/incidents/results/export").content == destino.read_bytes()


def test_analisis_fallido_conserva_el_ultimo_resultado_valido(client):
    subir(client, CSV_REAL.read_bytes(), CSV_REAL.name)
    assert subir(client, b"").status_code == 422
    assert "registros_procesados,100," in client.get("/api/incidents/results/export").text


def test_exporta_el_ultimo_analisis(client):
    subir(client, CSV_REAL.read_bytes())
    subir(client, (CABECERA + "\n" + FILA_VALIDA + "\n").encode())
    assert "registros_procesados,1," in client.get("/api/incidents/results/export").text


# --- CORS -----------------------------------------------------------------------------


def test_cors_permite_el_backoffice_local(client):
    respuesta = client.options(
        "/api/incidents/analyze",
        headers={"Origin": "http://localhost:3002", "Access-Control-Request-Method": "POST"},
    )
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:3002"


def test_cors_rechaza_otros_origenes(client):
    respuesta = client.options(
        "/api/incidents/analyze",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in respuesta.headers


def test_cors_expone_content_disposition_para_la_descarga(client):
    subir(client, CSV_REAL.read_bytes())
    respuesta = client.get("/api/incidents/results/export", headers={"Origin": "http://localhost:3002"})
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:3002"
    assert "content-disposition" in respuesta.headers["access-control-expose-headers"].lower()
