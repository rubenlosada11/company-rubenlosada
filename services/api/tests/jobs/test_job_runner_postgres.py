"""Job runner contra PostgreSQL real (opcional): exclusión mutua entre hilos y entre **procesos** independientes,
bloqueo ante un candado sin confirmar, idempotencia y restricciones de la migración.

Se salta si no se define `JOBS_TEST_DATABASE_URL`, que debe apuntar a un PostgreSQL **local y desechable** con la
migración `20261115120000_job_runs.sql` aplicada (los tests borran sus propias filas de `job_runs`). Por seguridad
solo se aceptan `localhost` y `127.0.0.1`: nunca Supabase.

    $env:JOBS_TEST_DATABASE_URL = "postgresql+psycopg://postgres:@127.0.0.1:5432/postgres"
    uv run pytest tests/jobs/test_job_runner_postgres.py
"""

import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, make_url, text
from sqlalchemy.exc import DBAPIError

from app.jobs import job_runner as jr
from app.jobs.job_runner import COMPLETED, PROCESSING, JobAlreadyCompleted, JobAlreadyRunning, job_runs

URL = os.environ.get("JOBS_TEST_DATABASE_URL", "").strip()
API_ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 11, 14)

pytestmark = pytest.mark.skipif(not URL, reason="JOBS_TEST_DATABASE_URL sin definir (PostgreSQL local opcional)")


@pytest.fixture
def job(monkeypatch):
    """Nombre de job único por test (las filas de otros tests no interfieren) y limpieza al terminar."""
    if make_url(URL).host not in ("localhost", "127.0.0.1"):
        pytest.fail("JOBS_TEST_DATABASE_URL debe ser un PostgreSQL local y desechable")
    monkeypatch.setenv("DATABASE_URL", URL)
    name = f"pg_test_{uuid.uuid4().hex[:10]}"
    yield name
    with jr.job_runs_engine().begin() as connection:
        connection.execute(delete(job_runs).where(job_runs.c.job_name == name))


def test_only_one_of_many_concurrent_threads_acquires_the_lock(job):
    contenders = 12
    barrier = threading.Barrier(contenders)

    def contend(_):
        barrier.wait()  # todos a la vez
        try:
            return jr.acquire_job_run(job, DAY)["id"]
        except JobAlreadyRunning:
            return None

    with ThreadPoolExecutor(contenders) as pool:
        results = list(pool.map(contend, range(contenders)))
    winners = [run_id for run_id in results if run_id is not None]
    assert len(winners) == 1
    runs = jr.list_job_runs(job)
    assert [run["id"] for run in runs] == winners  # los perdedores no dejaron ninguna fila


CONTENDER = """
import sys, time
from datetime import date
from app.jobs import job_runner as jr
job, start_at = sys.argv[1], float(sys.argv[2])
while time.time() < start_at:
    time.sleep(0.001)
try:
    run = jr.acquire_job_run(job, date(2026, 11, 14))
    jr.update_job_status(run["id"], "processing")
    print("ACQUIRED", run["id"], flush=True)
    time.sleep(1.5)  # mantiene el candado mientras los demás lo intentan
    jr.update_job_status(run["id"], "completed")
except jr.JobAlreadyRunning:
    print("LOCKED", flush=True)
"""


def test_only_one_of_many_independent_processes_acquires_the_lock(job):
    """Procesos de Python distintos, cada uno con su conexión, que intentan adquirir en el mismo instante."""
    start_at = time.time() + 4  # margen para que todos arranquen e importen
    env = {**os.environ, "DATABASE_URL": URL, "PYTHONIOENCODING": "utf-8"}
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", CONTENDER, job, str(start_at)],
            cwd=API_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(6)
    ]
    outputs = [process.communicate(timeout=60) for process in processes]
    assert all(process.returncode == 0 for process in processes), [err for _, err in outputs]
    lines = [out.strip().split()[0] for out, _ in outputs]
    assert lines.count("ACQUIRED") == 1 and lines.count("LOCKED") == 5
    runs = jr.list_job_runs(job)
    assert [run["status"] for run in runs] == [COMPLETED]


def test_a_contender_waits_for_an_uncommitted_lock_and_then_is_rejected(job):
    """Mientras la transacción que inserta el `pending` no confirma, el segundo `INSERT` espera; al confirmar, falla."""
    engine = jr.job_runs_engine()
    holder = engine.connect()
    transaction = holder.begin()
    holder.execute(
        job_runs.insert().values(id=uuid.uuid4(), job_name=job, target_date=DAY, status="pending", created_at=jr._now(None))
    )
    outcome = {}

    def contender():
        try:
            jr.acquire_job_run(job, DAY)
            outcome["result"] = "acquired"
        except JobAlreadyRunning:
            outcome["result"] = "locked"

    thread = threading.Thread(target=contender)
    thread.start()
    thread.join(timeout=1.5)
    assert thread.is_alive()  # bloqueado por el índice único, sin haber decidido todavía
    transaction.commit()
    holder.close()
    thread.join(timeout=10)
    assert outcome["result"] == "locked"


def test_a_contender_acquires_if_the_uncommitted_lock_is_rolled_back(job):
    engine = jr.job_runs_engine()
    holder = engine.connect()
    transaction = holder.begin()
    holder.execute(
        job_runs.insert().values(id=uuid.uuid4(), job_name=job, target_date=DAY, status="pending", created_at=jr._now(None))
    )
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.update(run=jr.acquire_job_run(job, DAY)))
    thread.start()
    thread.join(timeout=1.5)
    assert thread.is_alive()
    transaction.rollback()
    holder.close()
    thread.join(timeout=10)
    assert outcome["run"]["status"] == "pending"


def test_a_date_completed_while_waiting_for_the_lock_is_not_repeated(job):
    """Carrera de idempotencia: B espera el candado de A; A completa la fecha; B no la repite ni deja filas."""
    first = jr.acquire_job_run(job, DAY)
    jr.update_job_status(first["id"], PROCESSING)
    engine = jr.job_runs_engine()
    holder = engine.connect()
    transaction = holder.begin()
    holder.execute(
        job_runs.update()
        .where(job_runs.c.id == first["id"])
        .values(status=COMPLETED, finished_at=jr._now(None))
    )
    outcome = {}

    def contender():
        try:
            jr.acquire_job_run(job, DAY)
            outcome["result"] = "acquired"
        except JobAlreadyCompleted:
            outcome["result"] = "already completed"
        except JobAlreadyRunning:
            outcome["result"] = "locked"

    thread = threading.Thread(target=contender)
    thread.start()
    thread.join(timeout=1.5)
    assert thread.is_alive()  # el `processing` de A (aún sin confirmar su cambio) retiene el candado
    transaction.commit()
    holder.close()
    thread.join(timeout=10)
    assert outcome["result"] == "already completed"
    assert [run["status"] for run in jr.list_job_runs(job, DAY)] == [COMPLETED]


def test_postgres_check_constraints_reject_invalid_states(job):
    run = jr.create_job_run(job, DAY)
    with pytest.raises(DBAPIError) as error:
        with jr.job_runs_engine().begin() as connection:
            connection.execute(text("update job_runs set status = 'cancelled' where id = :id"), {"id": run["id"]})
    assert getattr(error.value.orig, "sqlstate", None) == "23514"


def test_failed_runs_release_the_lock_and_can_be_retried(job):
    run = jr.acquire_job_run(job, DAY)
    jr.update_job_status(run["id"], PROCESSING)
    jr.update_job_status(run["id"], "failed", error_message="PipelineError")
    retry = jr.acquire_job_run(job, DAY)
    assert retry["id"] != run["id"]
    assert [r["status"] for r in jr.list_job_runs(job, DAY)] == ["failed", "pending"]
