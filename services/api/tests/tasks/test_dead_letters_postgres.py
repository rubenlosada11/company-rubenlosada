"""DLQ contra PostgreSQL real (opcional): migración, `ON CONFLICT (task_id) DO NOTHING`, restricciones, RLS y
concurrencia.

Se salta si no se define `TASKS_TEST_DATABASE_URL`, que debe apuntar a un PostgreSQL **local y desechable** con la
migración `20261116120000_task_dead_letters.sql` aplicada (y los roles de Supabase `anon`, `authenticated` y
`service_role` creados antes, como en el resto de migraciones). Los tests vacían `task_dead_letters`. Por seguridad solo
se aceptan `localhost` y `127.0.0.1`: nunca Supabase.

    $env:TASKS_TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:15432/trackflow"
    uv run pytest tests/tasks/test_dead_letters_postgres.py
"""

import os
import threading
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError

from app.tasks import dead_letters

URL = os.environ.get("TASKS_TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(not URL, reason="TASKS_TEST_DATABASE_URL sin definir (PostgreSQL local opcional)")


@pytest.fixture(autouse=True)
def postgres(monkeypatch):
    if make_url(URL).host not in ("localhost", "127.0.0.1"):
        pytest.fail("TASKS_TEST_DATABASE_URL debe ser un PostgreSQL local y desechable")
    monkeypatch.setenv("DATABASE_URL", URL)
    with dead_letters.dead_letters_engine().begin() as connection:
        connection.execute(text("truncate public.task_dead_letters"))


def record(task_id: str, **overrides) -> bool:
    fields = {
        "task_id": task_id,
        "task_name": "reporting.run_weekly_performance",
        "reason": "retries_exhausted",
        "error": ConnectionError("base no disponible"),
        "attempts": 4,
        "max_retries": 3,
        "kwargs": {"week_start": "2026-11-09", "weeks": 2},
        "worker": "celery@worker",
    }
    return dead_letters.record(**{**fields, **overrides})


def test_the_engine_is_postgres_and_does_not_create_the_table():
    engine = dead_letters.dead_letters_engine()
    assert engine.dialect.name == "postgresql"


def test_idempotent_insert_on_postgres():
    task_id = str(uuid.uuid4())
    assert record(task_id) is True
    assert record(task_id, reason="permanent_error") is False
    row = dead_letters.get(task_id)
    assert row["reason"] == "retries_exhausted" and row["task_kwargs"] == {"week_start": "2026-11-09", "weeks": 2}
    assert row["failed_at"].tzinfo is not None


def test_concurrent_reports_of_the_same_failure_store_one_row():
    task_id = str(uuid.uuid4())
    barrier = threading.Barrier(8)
    results: list[bool] = []

    def report():
        barrier.wait()
        results.append(record(task_id))

    threads = [threading.Thread(target=report) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False] * 7 + [True]
    with dead_letters.dead_letters_engine().connect() as connection:
        count = connection.execute(
            text("select count(*) from public.task_dead_letters where task_id = :id"), {"id": task_id}
        ).scalar()
    assert count == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [("reason", "'otra'"), ("attempts", "0")],
)
def test_database_constraints(column, value):
    values = {"reason": "'expired'", "attempts": "1"} | {column: value}
    statement = text(
        "insert into public.task_dead_letters (task_id, task_name, reason, attempts, exception_type, error_message, "
        f"failed_at) values ('x', 't', {values['reason']}, {values['attempts']}, 'E', 'm', now())"
    )
    with pytest.raises(IntegrityError):
        with dead_letters.dead_letters_engine().begin() as connection:
            connection.execute(statement)


def test_row_level_security_and_privileges():
    with dead_letters.dead_letters_engine().connect() as connection:
        rls = connection.execute(
            text("select relrowsecurity from pg_class where oid = 'public.task_dead_letters'::regclass")
        ).scalar()
        privileges = {
            role: connection.execute(
                text("select has_table_privilege(:role, 'public.task_dead_letters', 'select')"), {"role": role}
            ).scalar()
            for role in ("anon", "authenticated", "service_role")
        }
    assert rls is True
    assert privileges == {"anon": False, "authenticated": False, "service_role": True}
