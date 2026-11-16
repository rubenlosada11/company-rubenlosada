"""Tareas asíncronas con Celery y Redis (DEV-55). Documentación: docs/async-tasks.md.

- `base.py`: clase base de las tareas: reintentos con backoff exponencial y Dead Letter Queue al fallar del todo.
- `reporting.py`: tarea de negocio, el pipeline semanal de desempeño (antes síncrono en
  `POST /reporting/pipeline-runs`).
- `diagnostics.py`: `diagnostics.ping`, comprobación mínima de que API, broker y worker se comunican.
- `queue.py`: productor (registra el dueño y encola) y lectura del estado para `GET /tasks/{task_id}`.
- `registry.py`: registro de las tareas encoladas por la API (dueño, nombre), en Redis.
- `dead_letters.py`: DLQ persistente (`task_dead_letters`, en la base de `DATABASE_URL`).
- `observability.py`: logs estructurados (JSON) del ciclo de vida de cada tarea.

La instancia de Celery está en `app/celery_app.py` (`celery -A app.celery_app worker`).
"""
