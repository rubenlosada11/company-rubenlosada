"""Etapas con entrada/salida del Reporte Semanal de Desempeño por Almacén y Cliente.

- `extract`: lee `telemetry_events` (solo lectura).
- `observe`: señales de salud del origen y cobertura frente al inventario (solo lectura, no crítica).
- `load`: upsert idempotente en `reporting.weekly_warehouse_client_performance`.
- `evaluation`: snapshot JSON de cada ejecución en `data/eval/` (no crítica).

Las transformaciones puras están en `data/process/weekly_performance/`; la orquestación (flows y tasks de Prefect), en
`data/pipelines/pipeline.py`. El acceso a la base reutiliza la capa de la API (`app.database`, `app.telemetry.storage`,
`app.reporting.tables`): un solo `DATABASE_URL` y una sola declaración de cada tabla.
"""
