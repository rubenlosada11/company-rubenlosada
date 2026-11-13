"""Pipelines de reporte de TrackFlow (esquema `reporting`).

Hoy contiene un único pipeline: el **Reporte Semanal de Desempeño por Almacén y Cliente**
(`weekly_warehouse_client_performance`). Diseño: `docs/reporting/PIPELINE_DESIGN.md`; operación:
`docs/reporting/weekly-performance-pipeline.md`.

Es el equivalente en este repositorio del `services/reporting/` del BRIEFING: vive dentro de la API, como la telemetría
(`app/telemetry/`), y no importa nada del reporte técnico de telemetría (`analysis.py`, `report.py`).

Estructura (un flow con subflows, cada uno probado por separado):

- `weeks`: semanas ISO en UTC y ventana de cálculo.
- `extract` → `validate` → `aggregate` → `load`: los cuatro subflows.
- `runs`: registro de ejecuciones (`reporting.pipeline_runs`).
- `flow`: `run_weekly_performance`, que encadena los subflows y registra la ejecución.
- `queries`: lecturas para los endpoints de `app/routes/reporting.py`.
- `__main__`: línea de comandos (`python -m app.reporting`), la que ejecuta el `cron` semanal.
"""
