"""Modelos de entrada y salida de los endpoints `/reporting` (contrato del BRIEFING §6)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.reporting.weeks import DEFAULT_WEEKS, MAX_WEEKS


def _as_utc(value: datetime | None) -> datetime | None:
    # SQLite devuelve las fechas sin zona horaria: se guardan siempre en UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class WeeklyPerformanceEntry(BaseModel):
    warehouse: Literal["los_angeles", "zaragoza"] = Field(description="Almacén.")
    client_id: str = Field(description="Cliente (marca B2B): slug de `SKU.client_name`.")
    inbound_units_count: int = Field(description="Volumen de entrada: unidades recibidas en la semana.")
    outbound_orders_count: int = Field(description="Throughput de salida: pedidos despachados en la semana.")
    stockout_events_count: int = Field(description="Frecuencia de quiebre de stock: veces bajo el mínimo.")
    discrepancy_events_count: int = Field(description="Discrepancias de inventario detectadas en la semana.")
    discrepancy_rate: float = Field(
        description="discrepancy_events_count / outbound_orders_count (0 sin pedidos; puede superar 1)."
    )


class WeeklyPerformanceReport(BaseModel):
    week_start: date = Field(description="Lunes de la semana ISO (UTC).")
    computed_at: datetime | None = Field(description="Fin de la última ejecución que calculó la semana (UTC).")
    run_id: uuid.UUID | None = Field(description="Ejecución (pipeline-runs) que calculó la semana por última vez.")
    entries: list[WeeklyPerformanceEntry] = Field(
        description="Una entrada por almacén y cliente con actividad; vacía si la semana se calculó sin actividad."
    )

    @field_validator("computed_at")
    @classmethod
    def coerce_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class PipelineRunRequest(BaseModel):
    """Parámetros opcionales de una ejecución manual. Sin cuerpo: las 2 últimas semanas completas."""

    model_config = ConfigDict(extra="forbid")

    week_start: date | None = Field(
        default=None, description="Semana más reciente a calcular (un lunes ya terminado). Por defecto, la última."
    )
    weeks: int = Field(
        default=DEFAULT_WEEKS, ge=1, le=MAX_WEEKS, description="Cuántas semanas hacia atrás, incluida `week_start`."
    )


class PipelineRun(BaseModel):
    id: uuid.UUID
    pipeline: str = Field(description="Nombre del pipeline.")
    status: Literal["running", "succeeded", "failed"]
    trigger: Literal["api", "cli"] = Field(description="`api` (POST) o `cli` (manual o cron).")
    triggered_by: str | None = Field(description="Id interno del usuario que la lanzó por la API.")
    request_id: uuid.UUID | None = Field(description="X-Request-Id de la petición que la lanzó (trigger = api).")
    environment: str = Field(description="Entorno de los eventos leídos (`TELEMETRY_ENVIRONMENT`).")
    week_from: date = Field(description="Primera semana (lunes) de la ventana.")
    week_to: date = Field(description="Última semana (lunes) de la ventana.")
    phase: Literal["started", "extracted", "validated", "aggregated", "loaded"] = Field(
        description="Última etapa completada (checkpoint): en una ejecución fallida, dónde se paró."
    )
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    events_read: int | None = Field(description="Eventos leídos de telemetry_events.")
    events_rejected: int | None = Field(description="Eventos excluidos por las reglas de calidad.")
    rows_upserted: int | None = Field(description="Filas escritas (insertadas o actualizadas).")
    rows_deleted: int | None = Field(description="Filas eliminadas al reconciliar las semanas recalculadas.")
    stats: dict[str, Any] | None = Field(
        description=(
            "Semanas, eventos leídos y rechazados, avisos (`warnings`), salud del origen por día, cobertura de la "
            "captura frente al inventario, cambios por semana (`changes`), `outcome`, etapas opcionales fallidas "
            "(`degraded`), snapshot de evaluación y datos de Prefect (flow run, caché de la transformación)."
        )
    )
    error: str | None = Field(description="Tipo de error si ha fallado (nunca datos ni credenciales).")

    @computed_field(
        description=(
            "Resultado legible: `running`, `succeeded` (todas las etapas), `partial` (reporte cargado, pero falló una "
            "etapa opcional: ver `stats.degraded`) o `failed` (no se cargó nada)."
        )
    )
    @property
    def outcome(self) -> Literal["running", "succeeded", "partial", "failed"]:
        if self.status == "succeeded" and (self.stats or {}).get("outcome") == "partial":
            return "partial"
        return self.status

    @field_validator("started_at", "finished_at")
    @classmethod
    def coerce_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
