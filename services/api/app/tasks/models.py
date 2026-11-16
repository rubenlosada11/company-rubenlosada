"""Contratos HTTP de las tareas asíncronas: `202` del productor, `GET /tasks/{task_id}` y la DLQ."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TaskAccepted(BaseModel):
    task_id: str = Field(description="Identificador de la tarea encolada. Consulta su estado en GET /tasks/{task_id}.")


class TaskError(BaseModel):
    type: Literal["retries_exhausted", "permanent_error", "time_limit", "expired", "unknown"] = Field(
        description="Tipo de fallo definitivo (el mismo vocabulario que `reason` en la DLQ)."
    )
    message: str = Field(description="Mensaje controlado: nunca trazas, credenciales ni datos internos.")


class TaskStatus(BaseModel):
    task_id: str
    task_name: str = Field(description="Tarea de Celery, p. ej. `reporting.run_weekly_performance`.")
    status: Literal["pending", "started", "retrying", "success", "failure"] = Field(
        description=(
            "`pending` (en la cola), `started` (un worker la ejecuta), `retrying` (falló de forma transitoria y "
            "espera su reintento), `success` (con `result`) o `failure` (con `error`; fallo definitivo, en la DLQ)."
        )
    )
    submitted_at: datetime = Field(description="Momento en que la API la encoló (UTC).")
    result: dict[str, Any] | None = Field(
        description="Resultado cuando `status` es `success` (en el pipeline semanal, la ejecución registrada)."
    )
    error: TaskError | None = Field(description="Fallo definitivo cuando `status` es `failure`.")


class DeadLetter(BaseModel):
    task_id: str
    task_name: str
    reason: Literal["retries_exhausted", "permanent_error", "time_limit", "expired"]
    attempts: int | None = Field(description="Intento en el que falló del todo (1 = inicial; 4 = tras 3 reintentos).")
    max_retries: int | None
    exception_type: str = Field(description="Tipo de la causa raíz del error.")
    error_message: str = Field(description="Cadena completa de errores, con las credenciales censuradas.")
    task_kwargs: dict[str, Any] | None = Field(description="Argumentos escalares de la tarea (sin datos sensibles).")
    worker: str | None
    failed_at: datetime

    @field_validator("failed_at")
    @classmethod
    def coerce_utc(cls, value: datetime) -> datetime:
        # SQLite devuelve las fechas sin zona horaria: se guardan siempre en UTC.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
