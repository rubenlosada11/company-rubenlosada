"""Gestión de errores transversal de la API: 500 genérico dentro de CORS, 422 sin los valores recibidos, fallos del
fichero de la base de datos y logs sin datos personales (`app/errors.py`, `app/database.py`)."""

import json
import logging

import pytest
from conftest import PASSWORD, bearer
from fastapi.testclient import TestClient

from app.database import StorageError, auth_db, incidents_table, suppliers_table
from app.main import app
from app.routes import suppliers
from app.routes.incidents import nombre_seguro

ORIGIN = {"Origin": "http://localhost:3002"}
GENERIC_500 = {"detail": "Error interno del servidor."}
SUPPLIER = {
    "name": "X", "country": "Spain", "categories": ["reverse_logistics"], "rate_per_shipment": 1.0,
    "currency": "EUR", "status": "active",
}


# --- 500 genérico, legible desde el navegador -------------------------------------------------------------------


def test_unexpected_500_outside_the_incident_router_keeps_cors_headers(client, monkeypatch, caplog):
    def explode(*args, **kwargs):
        raise RuntimeError("detalle interno: C:\\ruta\\secreta")

    monkeypatch.setattr(suppliers, "to_supplier", explode)
    with caplog.at_level(logging.ERROR, logger="trackflow"):
        response = client.post("/suppliers", json=SUPPLIER, headers=ORIGIN)

    assert (response.status_code, response.json()) == (500, GENERIC_500)
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    # Sin esta cabecera el navegador trata la respuesta como un fallo de red («la API está apagada»).
    assert response.headers["access-control-allow-origin"] == "http://localhost:3002"
    assert "secreta" not in response.text and "Traceback" not in response.text and "RuntimeError" not in response.text
    assert "detalle interno" in caplog.text and "POST /suppliers" in caplog.text  # la traza queda en el log


def test_unexpected_500_does_not_need_raise_server_exceptions_disabled(client, monkeypatch):
    """El error se convierte en respuesta: no se propaga al servidor (ni al cliente de pruebas)."""
    monkeypatch.setattr(suppliers, "to_supplier", lambda _: 1 / 0)
    assert client.post("/suppliers", json=SUPPLIER).status_code == 500


def test_http_errors_are_not_turned_into_500(client, anon_client):
    assert client.get("/suppliers/999").status_code == 404
    assert anon_client.get("/suppliers").status_code == 401
    assert client.get("/no-existe").status_code == 404


# --- Fichero de la base de datos ilegible ------------------------------------------------------------------------


def test_corrupt_suppliers_file_is_a_generic_500_with_cors_and_a_clear_log(client, db_path, caplog):
    db_path.write_text("{corrupto", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="trackflow"):
        response = client.get("/suppliers", headers=ORIGIN)

    assert (response.status_code, response.json()) == (500, GENERIC_500)
    assert response.headers["access-control-allow-origin"] == "http://localhost:3002"
    assert str(db_path) not in response.text
    # El log dice qué base falla y por qué, en una línea y sin el contenido del fichero.
    assert "No se puede usar la base de datos" in caplog.text and str(db_path) in caplog.text
    assert "no contiene JSON válido" in caplog.text
    assert "Traceback" not in caplog.text and "corrupto" not in caplog.text


def test_corrupt_auth_file_is_a_generic_500_on_login(anon_client, auth_env):
    auth_env.parent.mkdir(parents=True, exist_ok=True)
    auth_env.write_text("no es json", encoding="utf-8")
    response = anon_client.post("/auth/login", json={"email": "ana@trackflow.test", "password": PASSWORD})
    assert (response.status_code, response.json()) == (500, GENERIC_500)


def test_corrupt_incidents_file_is_a_generic_500(client, incidents_db_path):
    incidents_db_path.parent.mkdir(parents=True, exist_ok=True)
    incidents_db_path.write_bytes(b"\xff\xfe no es utf-8")
    response = client.get("/api/incidents")
    assert (response.status_code, response.json()) == (500, GENERIC_500)


@pytest.mark.parametrize("opener", [suppliers_table, auth_db, incidents_table])
def test_storage_error_names_the_file_and_the_reason(opener, db_path, auth_env, incidents_db_path):
    for path in (db_path, auth_env, incidents_db_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{corrupto", encoding="utf-8")

    with pytest.raises(StorageError) as raised, opener() as handle:
        handle.all() if hasattr(handle, "all") else handle.tables()

    assert "no contiene JSON válido (línea 1" in str(raised.value)
    assert isinstance(raised.value.__cause__, json.JSONDecodeError)
    assert raised.value.path in (db_path, auth_env, incidents_db_path)


def test_storage_error_when_the_path_cannot_be_opened(tmp_path, monkeypatch):
    # La ruta es una carpeta: el sistema no puede abrirla como fichero.
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(tmp_path))
    with pytest.raises(StorageError, match="No se puede usar la base de datos"), suppliers_table() as table:
        table.all()


def test_storage_error_does_not_hide_other_errors(db_path):
    with pytest.raises(KeyError), suppliers_table():
        raise KeyError("otro error")


def test_lock_is_released_after_a_storage_error(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("{corrupto", encoding="utf-8")
    with pytest.raises(StorageError), suppliers_table() as table:
        table.all()
    db_path.write_text("{}", encoding="utf-8")
    with suppliers_table() as table:  # se quedaría bloqueado si el candado siguiera tomado
        assert table.all() == []


# --- 422 sin los valores recibidos -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "payload", "secret"),
    [
        ("/auth/login", {"email": "ana@trackflow.test", "password": 987654321012}, "987654321012"),
        ("/users", {"email": "nueva@trackflow.test", "password": "zq9!x"}, "zq9!x"),
        ("/auth/reset-password", {"token": "token-secreto-del-enlace", "new_password": "zq9!x"}, "zq9!x"),
        ("/users", {"email": "no-es-un-email-secreto", "password": PASSWORD}, "no-es-un-email-secreto"),
    ],
)
def test_422_does_not_echo_the_received_values(anon_client, path, payload, secret):
    response = anon_client.post(path, json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert secret not in response.text
    for item in response.json()["detail"]:
        assert set(item) <= {"type", "loc", "msg"} and {"loc", "msg"} <= set(item)


def test_422_keeps_the_contract_the_backoffice_reads(client):
    response = client.post("/suppliers", json={**SUPPLIER, "rate_per_shipment": 0})
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"type": "greater_than", "loc": ["body", "rate_per_shipment"], "msg": "Input should be greater than 0"}
    ]


def test_422_of_own_validators_keeps_the_message_in_spanish(client):
    response = client.post("/suppliers", json={**SUPPLIER, "contact_email": "sin-arroba"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, contact_email no tiene un formato de email válido"
    assert "sin-arroba" not in response.text


def test_422_with_cors_headers(anon_client):
    response = anon_client.post("/auth/login", json={}, headers=ORIGIN)
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == "http://localhost:3002"


def test_incident_manager_still_answers_400_with_its_own_format(client):
    response = client.post("/api/incidents", json={"title": ""})
    assert response.status_code == 400
    assert {"field", "loc", "msg"} == set(response.json()["detail"][0])


# --- Logs sin datos personales -----------------------------------------------------------------------------------


def test_log_of_a_corrupt_stored_user_does_not_contain_its_data(anon_client, make_user, caplog):
    user = make_user("privado@trackflow.test")
    with auth_db() as db:
        db.table("users").update({"role": "rol-que-no-existe"})

    with caplog.at_level(logging.DEBUG):
        response = anon_client.get("/auth/me", headers=bearer(user))

    assert (response.status_code, response.json()) == (500, GENERIC_500)
    # Qué modelo y qué campo fallan, y dónde; nunca el documento guardado (email, hash de la contraseña).
    assert "no cumplen el modelo User" in caplog.text and "role (enum)" in caplog.text
    assert "services" in caplog.text and "users.py" in caplog.text
    for private in ("privado@trackflow.test", user.hashed_password, "rol-que-no-existe"):
        assert private not in caplog.text


@pytest.mark.parametrize(
    ("received", "expected"),
    [
        ("incidencias.csv", "incidencias.csv"),
        ("C:\\Users\\ana\\Documents\\incidencias.csv", "incidencias.csv"),
        ("../../etc/incidencias.csv", "incidencias.csv"),
        ("a.csv\r\nERROR: línea falsa en el log", "a.csvERROR: línea falsa en el log"),
        ("x" * 300 + ".csv", "x" * 120),
    ],
)
def test_uploaded_file_name_is_sanitised_for_logs_and_messages(received, expected):
    assert nombre_seguro(received) == expected


# --- Arranque --------------------------------------------------------------------------------------------------


def test_startup_with_invalid_config_logs_a_clear_line(monkeypatch, caplog):
    from app.security import ConfigError

    monkeypatch.setenv("SECRET_KEY", "change-me")
    with caplog.at_level(logging.ERROR, logger="trackflow"), pytest.raises(ConfigError), TestClient(app):
        pass
    assert "La API no puede arrancar: SECRET_KEY" in caplog.text
