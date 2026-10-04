"""Tests de la lógica compartida: carga, validación, métricas y exportación."""

import csv
import io

import pytest

from analisis_incidencias import (
    CABECERA_EXPORTACION,
    ErrorAnalisis,
    analizar,
    decodificar_csv,
    generar_csv,
    generar_csv_bytes,
    leer_csv,
    parsear_csv,
    validar_registro,
)
from analisis_incidencias.dominio import CAMPOS

CABECERA = ",".join(CAMPOS)

REGISTRO_VALIDO = {
    "incident_id": "TRF-000001",
    "date": "2024-01-15",
    "country": "ES",
    "customer_type": "B2C",
    "tracking_number": "ES12345678",
    "carrier": "SEUR",
    "category": "DAMAGE",
    "description": "Caja aplastada",
    "status": "CLOSED",
    "customer_email": "persona@example.com",
    "satisfaction_score": "4",
}


def registro(**cambios):
    return {**REGISTRO_VALIDO, **cambios}


def csv_de(*registros):
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=CAMPOS, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(registros)
    return salida.getvalue()


def analizar_texto(texto):
    return analizar(parsear_csv(texto), "x.csv")


# --- Validación --------------------------------------------------------------


def test_registro_valido_no_tiene_errores():
    assert validar_registro(registro()) == []


@pytest.mark.parametrize(
    ("cambios", "regla"),
    [
        ({"country": ""}, "pais_invalido"),
        ({"country": "MX"}, "pais_invalido"),
        ({"carrier": ""}, "transportista_invalido"),
        ({"carrier": "CORREOS"}, "transportista_invalido"),
        ({"carrier": "UPS"}, "transportista_invalido"),  # carrier de US declarado en ES
        ({"tracking_number": ""}, "tracking_invalido"),
        ({"tracking_number": "1234567"}, "tracking_invalido"),
        ({"category": ""}, "categoria_invalida"),
        ({"category": "OTHER"}, "categoria_invalida"),
        ({"description": "roto"}, "descripcion_invalida"),
        ({"customer_email": ""}, "email_invalido"),
        ({"customer_email": "sin-arroba.com"}, "email_invalido"),
        ({"satisfaction_score": ""}, "cerrada_sin_puntuacion"),
        ({"satisfaction_score": "0"}, "puntuacion_fuera_rango"),
        ({"satisfaction_score": "6"}, "puntuacion_fuera_rango"),
        ({"satisfaction_score": "3.5"}, "puntuacion_fuera_rango"),
        ({"satisfaction_score": "abc"}, "puntuacion_fuera_rango"),
        ({"incident_id": "TRF-1"}, "id_invalido"),
        ({"date": "15/01/2024"}, "fecha_invalida"),
        ({"date": "2024-02-30"}, "fecha_invalida"),
        ({"customer_type": "B2X"}, "tipo_cliente_invalido"),
        ({"status": "PENDING"}, "estado_invalido"),
        ({"status": "closed"}, "estado_invalido"),  # los valores del CONTEXT son exactos
    ],
)
def test_cada_regla_se_detecta(cambios, regla):
    assert validar_registro(registro(**cambios)) == [regla]


def test_limites_minimos_son_validos():
    assert validar_registro(registro(tracking_number="12345678", description="Roto")) == ["descripcion_invalida"]
    assert validar_registro(registro(tracking_number="12345678", description="Rotos")) == []


def test_pais_invalido_no_duplica_error_de_carrier_conocido():
    assert validar_registro(registro(country="", carrier="SEUR")) == ["pais_invalido"]
    assert validar_registro(registro(country="", carrier="XYZ")) == ["pais_invalido", "transportista_invalido"]


# --- Métricas ----------------------------------------------------------------


def test_puntuacion_en_incidencia_abierta_es_valida_pero_no_cuenta():
    resultado = analizar_texto(csv_de(registro(status="OPEN", satisfaction_score="1"), registro()))
    assert resultado["totales"]["invalidos"] == 0
    assert resultado["satisfaccion"]["con_puntuacion"] == 1
    assert resultado["satisfaccion"]["media"] == 4.0


def test_registro_con_varias_reglas_cuenta_una_vez_como_invalido():
    resultado = analizar_texto(csv_de(registro(category="", customer_email="x"), registro()))
    assert resultado["totales"] == {"procesados": 2, "validos": 1, "invalidos": 1}
    assert resultado["invalidos_por_regla"]["categoria_invalida"] == 1
    assert resultado["invalidos_por_regla"]["email_invalido"] == 1
    assert resultado["registros_invalidos"] == [
        {"linea": 2, "incident_id": "TRF-000001", "reglas": ["categoria_invalida", "email_invalido"]}
    ]


def test_invalidos_no_participan_en_metricas():
    resultado = analizar_texto(csv_de(registro(), registro(incident_id="TRF-000002", category="LOST")))
    assert sum(resultado["por_categoria"].values()) == 1
    assert resultado["satisfaccion"]["con_puntuacion"] == 1


def test_sin_cerradas_la_media_es_none():
    assert analizar_texto(csv_de(registro(status="OPEN", satisfaction_score="")))["satisfaccion"]["media"] is None


def test_agrupacion_por_fecha():
    resultado = analizar_texto(csv_de(
        registro(date="2024-01-01"),  # lunes, semana ISO 1
        registro(incident_id="TRF-000002", date="2024-04-07"),  # domingo, T2
    ))
    por_fecha = resultado["por_fecha"]
    assert por_fecha["mes"] == {"2024-01": 1, "2024-04": 1}
    assert por_fecha["trimestre"] == {"2024-T1": 1, "2024-T2": 1}
    assert por_fecha["semana"] == {"2024-S01": 1, "2024-S14": 1}
    assert por_fecha["dia_semana"]["lunes"] == 1 and por_fecha["dia_semana"]["domingo"] == 1


def test_resultado_no_contiene_correos():
    resultado = analizar_texto(csv_de(registro(), registro(customer_email="x")))
    assert "persona@example.com" not in repr(resultado)


# --- Carga y estructura del fichero ------------------------------------------


def test_fila_con_columnas_de_menos_es_invalida():
    filas = parsear_csv(CABECERA + "\nTRF-000001,2024-01-15,ES\n")
    assert "fila_mal_formada" in validar_registro(filas[0].datos, filas[0].columnas_ok)


def test_lineas_en_blanco_se_ignoran():
    assert len(parsear_csv(csv_de(registro()) + "\n\n")) == 1


@pytest.mark.parametrize(
    ("texto", "mensaje"),
    [
        ("", "vacío"),
        ("   \n", "vacío"),
        (CABECERA + "\n", "no contiene registros"),
        ("incident_id,date\nTRF-000001,2024-01-01\n", "Faltan columnas obligatorias"),
    ],
)
def test_errores_de_estructura(texto, mensaje):
    with pytest.raises(ErrorAnalisis, match=mensaje):
        parsear_csv(texto)


def test_decodificar_acepta_bom_y_rechaza_no_utf8():
    assert len(decodificar_csv(csv_de(registro()).encode("utf-8-sig"))) == 1
    with pytest.raises(ErrorAnalisis, match="UTF-8"):
        decodificar_csv(csv_de(registro(description="Paquete dañado")).encode("latin-1"))


def test_leer_csv_fichero_inexistente(tmp_path):
    with pytest.raises(ErrorAnalisis, match="no existe"):
        leer_csv(tmp_path / "no-existe.csv")


def test_leer_csv_ruta_es_directorio(tmp_path):
    with pytest.raises(ErrorAnalisis, match="no es un fichero"):
        leer_csv(tmp_path)


# --- Exportación ---------------------------------------------------------------


def test_exportacion_una_fila_por_metrica():
    resultado = analizar_texto(csv_de(registro(), registro(incident_id="TRF-000002", status="OPEN")))
    filas = list(csv.reader(io.StringIO(generar_csv(resultado))))
    assert filas[0] == list(CABECERA_EXPORTACION)
    assert all(len(fila) == 4 for fila in filas)
    indice = {(f[0], f[1]): f[2:] for f in filas[1:]}
    assert len(indice) == len(filas) - 1  # sin métricas duplicadas
    assert indice[("resumen", "registros_validos")] == ["2", ""]
    assert indice[("estado", "OPEN")] == ["1", "50.0"]
    assert indice[("satisfaccion", "media")] == ["4.0", ""]
    assert "@" not in generar_csv(resultado)


def test_exportacion_en_bytes_lleva_bom_utf8():
    resultado = analizar_texto(csv_de(registro()))
    contenido = generar_csv_bytes(resultado)
    assert contenido.startswith(b"\xef\xbb\xbf")
    assert contenido.decode("utf-8-sig") == generar_csv(resultado)


def test_csv_mal_formado_no_muestra_el_error_interno():
    with pytest.raises(ErrorAnalisis) as error:
        parsear_csv(",".join(CAMPOS) + "\n" + "x" * 200_000 + "\n")
    assert str(error.value) == "El CSV está mal formado (cerca de la línea 2)."
    assert "field" not in str(error.value)
