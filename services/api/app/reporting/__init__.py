"""Reporting de TrackFlow dentro de la API: el «`services/reporting/`» del BRIEFING de pipelines (esquema `reporting`).

El cálculo **no** vive aquí: el ETL (extracción, transformación, carga) y su orquestación con Prefect 3 están en
`data/pipelines/pipeline.py` (flows y tasks) y `data/process/` (transformaciones puras). Diseño:
`data/pipelines/PIPELINE_DESIGN.md`; operación: `docs/reporting/weekly-performance-pipeline.md`.

Este paquete contiene solo lo que la API necesita para servir el reporte y lo que comparte con el pipeline:

- `tables`: tablas del esquema `reporting` y su motor (también las usa el pipeline para cargar).
- `runs`: registro de ejecuciones (`reporting.pipeline_runs`): el pipeline escribe, la API lee.
- `weeks`: semanas ISO en UTC y ventana de cálculo (la API valida `week_start` con las mismas reglas).
- `queries`: lecturas de la tabla del reporte para el endpoint.
- `models`: contrato JSON de los endpoints.
- `runner`: importa el flow de `data/pipelines/` para el `POST` (sin duplicar su lógica).

No importa nada del reporte técnico de telemetría (`app/telemetry/analysis.py`, `report.py`).
"""
