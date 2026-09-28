"""Tests de la CLI y del contrato con CONTEXT-incidencias.es.md usando el CSV real.

La lógica de validación y métricas se prueba en packages/analisis-incidencias/tests.
Ejecutar desde la raíz: python -m pytest scripts/tests packages/analisis-incidencias/tests
"""

import csv
import sys
from pathlib import Path

import pytest

DIR_SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIR_SCRIPTS))

import analyze  # noqa: E402

CSV_REAL = DIR_SCRIPTS / "incidents-trackflow.csv"


# --- CSV real contra los valores esperados de CONTEXT-incidencias.es.md ---


@pytest.fixture(scope="module")
def resultado_real():
    return analyze.analizar(analyze.leer_csv(CSV_REAL), CSV_REAL.name)


def test_totales_coinciden_con_context(resultado_real):
    assert resultado_real["totales"] == {"procesados": 100, "validos": 95, "invalidos": 5}


def test_invalidos_por_regla_coinciden_con_context(resultado_real):
    esperado = {
        "tracking_invalido": 1,
        "transportista_invalido": 1,
        "categoria_invalida": 1,
        "email_invalido": 1,
        "cerrada_sin_puntuacion": 1,
    }
    assert {k: v for k, v in resultado_real["invalidos_por_regla"].items() if v} == esperado


def test_categorias_coinciden_con_context(resultado_real):
    assert resultado_real["por_categoria"] == {
        "LOST_PARCEL": 14,
        "DELAYED_DELIVERY": 38,
        "WRONG_ADDRESS": 19,
        "RETURN_REQUEST": 17,
        "DAMAGE": 7,
    }


def test_estados_coinciden_con_context(resultado_real):
    assert resultado_real["por_estado"] == {"OPEN": 29, "CLOSED": 52, "DISCARDED": 14}


def test_paises_coinciden_con_context(resultado_real):
    assert resultado_real["por_pais"] == {"US": 50, "ES": 45}


def test_satisfaccion_coincide_con_context(resultado_real):
    s = resultado_real["satisfaccion"]
    assert (s["cerradas"], s["con_puntuacion"], s["media"]) == (52, 52, 3.06)
    assert s["distribucion"] == {"1": 6, "2": 11, "3": 15, "4": 14, "5": 6}


def test_metricas_extra_son_coherentes(resultado_real):
    validos = resultado_real["totales"]["validos"]
    assert sum(resultado_real["por_transportista"].values()) == validos
    assert sum(resultado_real["por_tipo_cliente"].values()) == validos
    for periodo in resultado_real["por_fecha"].values():
        assert sum(periodo.values()) == validos
    for cruce in resultado_real["cruces"].values():
        assert sum(sum(fila.values()) for fila in cruce.values()) == validos
    cruce_cat = resultado_real["cruces"]["transportista_categoria"]
    for categoria, total in resultado_real["por_categoria"].items():
        assert sum(fila[categoria] for fila in cruce_cat.values()) == total


def test_informe_muestra_valores_del_context(resultado_real):
    informe = analyze.formatear_informe(resultado_real)
    for fragmento in ("TOTAL DE REGISTROS", "100", "Media: 3.06 / 5.00", "Con puntuación: 52 de 52", "( 40.0%)"):
        assert fragmento in informe


# --- Privacidad y exportación -------------------------------------------------


def test_informe_y_exportacion_no_contienen_correos(resultado_real, tmp_path):
    correos = {f.datos["customer_email"] for f in analyze.leer_csv(CSV_REAL) if f.datos["customer_email"]}
    exportado = analyze.exportar_csv(resultado_real, tmp_path / "r.csv").read_text(encoding="utf-8-sig")
    salidas = analyze.formatear_informe(resultado_real) + exportado
    assert not any(correo in salidas for correo in correos)
    assert "@" not in salidas


def test_exportacion_real_una_fila_por_metrica(tmp_path, resultado_real):
    ruta = analyze.exportar_csv(resultado_real, tmp_path / "results.csv")
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f))
    indice = {(f[0], f[1]): f[2:] for f in filas[1:]}
    assert len(indice) == len(filas) - 1
    assert indice[("resumen", "registros_validos")] == ["95", ""]
    assert indice[("categoria", "DELAYED_DELIVERY")] == ["38", "40.0"]
    assert indice[("estado", "CLOSED")] == ["52", "54.7"]
    assert indice[("satisfaccion", "media")] == ["3.06", ""]
    assert indice[("invalidos", "email_invalido")] == ["1", ""]


# --- Pregunta de exportación ----------------------------------------------------


def respuestas(*valores):
    iterador = iter(valores)

    def leer(_prompt):
        valor = next(iterador)
        if isinstance(valor, BaseException):
            raise valor
        return valor

    return leer


@pytest.mark.parametrize("respuesta", ["s", "S", "sí", "si", "y", " s "])
def test_pregunta_acepta_si(respuesta):
    assert analyze.preguntar_exportacion(respuestas(respuesta)) is True


@pytest.mark.parametrize("respuesta", ["n", "N", "no"])
def test_pregunta_acepta_no(respuesta):
    assert analyze.preguntar_exportacion(respuestas(respuesta)) is False


def test_pregunta_repite_ante_respuesta_invalida(capsys):
    assert analyze.preguntar_exportacion(respuestas("quizá", "", "s")) is True
    assert capsys.readouterr().out.count("Respuesta no válida") == 2


@pytest.mark.parametrize("interrupcion", [EOFError(), KeyboardInterrupt()])
def test_pregunta_sin_entrada_no_exporta(interrupcion):
    assert analyze.preguntar_exportacion(respuestas(interrupcion)) is False


# --- CLI de extremo a extremo -----------------------------------------------


def test_main_exporta_con_s(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", respuestas("s"))
    destino = tmp_path / "results.csv"
    assert analyze.main([str(CSV_REAL), "--output", str(destino)]) == 0
    assert destino.exists()
    assert "Resultados exportados" in capsys.readouterr().out


def test_main_no_exporta_con_n(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", respuestas("n"))
    monkeypatch.chdir(tmp_path)
    assert analyze.main([str(CSV_REAL)]) == 0
    assert not (tmp_path / "results.csv").exists()
    salida = capsys.readouterr().out
    assert "TOTAL DE REGISTROS" in salida and "No se ha exportado" in salida


def test_main_fichero_inexistente(tmp_path, capsys):
    assert analyze.main([str(tmp_path / "nada.csv")]) == 1
    assert "no existe" in capsys.readouterr().err


def test_main_csv_vacio(tmp_path, capsys):
    vacio = tmp_path / "vacio.csv"
    vacio.write_text("")
    assert analyze.main([str(vacio)]) == 1
    assert "vacío" in capsys.readouterr().err


def test_main_sin_argumento():
    with pytest.raises(SystemExit) as salida:
        analyze.main([])
    assert salida.value.code == 2
