"""Instancia de Celery de TrackFlow: tareas asíncronas con Redis como broker y como result backend (DEV-55).

Arquitectura productor/consumidor (docs/async-tasks.md):

    Cliente → FastAPI (productor: valida y encola) → Redis (broker) → Celery worker (consumidor) → Redis (resultado)

- **Productor:** la API. Encola con `apply_async` y responde 202 con el `task_id` sin esperar al worker.
- **Broker:** Redis guarda los mensajes pendientes en una lista (cola `celery`) hasta que un worker los recoge.
- **Consumidor:** el worker, un proceso aparte que se arranca con

      celery -A app.celery_app worker --loglevel=INFO

  (desde `services/api`; en Windows sin Docker, añade `--pool=solo`). Parar la API no para el worker y parar el worker
  no hace que la API ejecute nada: los mensajes esperan en Redis.
- **Result backend:** el mismo Redis guarda el estado y el resultado de cada tarea (`GET /tasks/{task_id}`) durante
  `RESULT_TTL`. No confundir con la DLQ: los fallos definitivos se guardan además en la base de datos
  (`app/tasks/dead_letters.py`).

La URL de Redis sale **solo** de `REDIS_URL` (`get_redis_url`): la usan el broker, el result backend y el registro de
tareas de la API. Por defecto, el Redis local de desarrollo (`redis://127.0.0.1:6379/0`); en Docker Compose,
`redis://redis:6379/0`.
"""

import logging
import os
from datetime import timedelta

from celery import Celery
from sqlalchemy import make_url

# 127.0.0.1 y no `localhost`: en Windows `localhost` resuelve antes a ::1 (IPv6), donde Docker no publica Redis, y
# cada conexión perdía ~2 s por dirección (medido: primer POST en frío de 8,3 s, 503 de 4 s con Redis parado).
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"

# Tiempo máximo de ejecución de una tarea. Al llegar al límite «suave» Celery lanza `SoftTimeLimitExceeded` dentro de
# la tarea (que puede cerrar su registro); si sigue viva al llegar al «duro», el proceso hijo se mata. El pipeline
# semanal tarda segundos; con sus reintentos internos de base de datos (~42 s en la extracción y ~20 s en la carga)
# sigue muy por debajo de 5 minutos. Un límite superado no se reintenta (app/tasks/base.py).
TASK_SOFT_TIME_LIMIT = 300
TASK_TIME_LIMIT = 360

# Cuánto viven en Redis el estado y el resultado de una tarea (y su registro de dueño, app/tasks/registry.py).
RESULT_TTL = timedelta(days=1)

# Un mensaje que ningún worker ha empezado en este tiempo caduca: el worker lo descarta como `REVOKED` (y queda en la
# DLQ con el motivo `expired`) en lugar de ejecutar un pipeline pedido hace horas.
MESSAGE_EXPIRES = timedelta(hours=1)

# Con `acks_late`, Redis devuelve a la cola un mensaje entregado y no confirmado al pasar este tiempo (el worker murió
# sin confirmar). Debe superar con margen el tiempo máximo de una tarea (y la espera de sus reintentos), o Redis
# entregaría otra vez una tarea que sigue en marcha.
VISIBILITY_TIMEOUT = timedelta(hours=1)

# Conexión a Redis: fallar pronto. Sin esto, con Redis caído el `POST` productor tardaría decenas de segundos en
# responder 503.
CONNECT_TIMEOUT_SECONDS = 2


def get_redis_url() -> str:
    """URL de Redis (`REDIS_URL`). Única fuente de la dirección del broker para la API, el worker y Flower."""
    return os.environ.get("REDIS_URL", "").strip() or DEFAULT_REDIS_URL


def describe_redis_url(url: str | None = None) -> str:
    """`redis://host:puerto/db` sin usuario ni contraseña, para los logs."""
    try:
        parsed = make_url(url or get_redis_url())
    except Exception:  # noqa: BLE001 — una URL mal escrita no debe romper el arranque
        return "REDIS_URL no interpretable"
    return f"{parsed.drivername}://{parsed.host or 'localhost'}:{parsed.port or 6379}/{parsed.database or 0}"


def log_task_queue_config() -> None:
    """Al arrancar la API: qué Redis usa la cola (sin credenciales). No comprueba la conexión ni impide arrancar."""
    logger = logging.getLogger("trackflow.tasks")
    logger.info("Cola de tareas (Celery): broker y resultados en %s", describe_redis_url())


def create_celery_app() -> Celery:
    url = get_redis_url()
    app = Celery("trackflow", broker=url, backend=url, include=["app.tasks.reporting", "app.tasks.diagnostics"])
    app.conf.update(
        # --- Serialización: solo JSON (nunca pickle, que ejecutaría código al deserializar un mensaje ajeno) -------
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # --- Estados: `STARTED` además de PENDING/SUCCESS/FAILURE (Celery no lo publica por defecto) ---------------
        task_track_started=True,
        # --- ACK y reentrega ---------------------------------------------------------------------------------------
        # ACK tardío: el worker confirma el mensaje al TERMINAR la tarea, no al recibirlo. Si el worker muere a mitad,
        # el mensaje sigue en Redis y se vuelve a entregar (al reiniciar el worker o tras VISIBILITY_TIMEOUT). Es
        # seguro porque el pipeline es idempotente (recalcula y hace upsert de la ventana) y su candado de base de
        # datos impide dos ejecuciones a la vez. El ACK confirma la ENTREGA del mensaje; el resultado se guarda aparte
        # en el result backend.
        task_acks_late=True,
        # Si el proceso hijo muere (OOM, kill), el mensaje se rechaza y vuelve a la cola en lugar de darse por hecho.
        task_reject_on_worker_lost=True,
        # Un fallo o un timeout SÍ confirman el mensaje (valor por defecto, explícito): un fallo definitivo no debe
        # reentregarse en bucle; queda en el result backend y en la DLQ.
        task_acks_on_failure_or_timeout=True,
        # Un worker no reserva más mensajes de los que puede ejecutar: con tareas largas y ACK tardío, prefetch alto
        # dejaría mensajes bloqueados en un worker ocupado.
        worker_prefetch_multiplier=1,
        broker_transport_options={
            "visibility_timeout": int(VISIBILITY_TIMEOUT.total_seconds()),
            "socket_connect_timeout": CONNECT_TIMEOUT_SECONDS,
        },
        broker_connection_retry_on_startup=True,
        # Publicar un mensaje con Redis caído: un reintento corto y error (la API responde 503).
        task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.2},
        # --- Timeouts ----------------------------------------------------------------------------------------------
        task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
        task_time_limit=TASK_TIME_LIMIT,
        # --- Resultados --------------------------------------------------------------------------------------------
        result_expires=RESULT_TTL,
        redis_socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        # --- Monitorización (Flower): eventos de los workers y evento `task-sent` al encolar ----------------------
        worker_send_task_events=True,
        task_send_sent_event=True,
    )
    return app


celery_app = create_celery_app()

# Logs estructurados (JSON) de inicio, fin, reintento y fallo de cada tarea, mediante señales de Celery.
import app.tasks.observability  # noqa: E402, F401
