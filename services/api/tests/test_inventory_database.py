"""Tests del motor SQLModel del inventario (`app/database.py`: `get_engine`, `get_db`, `DATABASE_URL`)."""

import pytest
from sqlalchemy import inspect, make_url
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app import database
from app.inventory_models import StockEntry


def test_default_url_is_the_local_sqlite_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    url = database.get_database_url()
    assert url == f"sqlite:///{database.DEFAULT_INVENTORY_DB_PATH.as_posix()}"
    assert url.endswith("services/api/db/inventory.db")


def test_blank_database_url_falls_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    assert database.get_database_url().startswith("sqlite:///")


def test_engine_creates_the_three_tables(inventory_db_url):
    engine = database.get_engine()
    assert engine.url.database == inventory_db_url.removeprefix("sqlite:///")
    assert set(inspect(engine).get_table_names()) == {"skus", "stock_entries", "stock_exits"}


def test_engine_is_reused_and_replaced_when_the_url_changes(tmp_path, monkeypatch):
    first = database.get_engine()
    assert database.get_engine() is first
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'otra' / 'inventory.db').as_posix()}")
    second = database.get_engine()
    assert second is not first
    assert (tmp_path / "otra" / "inventory.db").exists()


def test_sqlite_enforces_foreign_keys():
    with Session(database.get_engine()) as session:
        session.add(StockEntry(sku_id=999, quantity=1, reference="X", warehouse="LA", user_uuid="u"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_get_db_yields_a_session_and_closes_it():
    dependency = database.get_db()
    session = next(dependency)
    assert isinstance(session, Session)
    with pytest.raises(StopIteration):
        next(dependency)


def test_postgresql_engine_uses_psycopg_with_a_connect_timeout(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(url=url, **kwargs)
        raise RuntimeError("sin conexión en el test")

    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:x@127.0.0.1:1/postgres")
    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    with pytest.raises(RuntimeError):
        database.get_engine()
    assert captured["connect_args"] == {"connect_timeout": database.POSTGRES_CONNECT_TIMEOUT_SECONDS}
    assert captured["pool_pre_ping"] is True
    assert make_url(captured["url"]).get_driver_name() == "psycopg"  # driver por defecto de SQLAlchemy 2.1
