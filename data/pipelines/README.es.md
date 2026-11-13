# Carpeta `data/pipelines`

Esta carpeta agrupa **todos los pipelines de datos del monorepo** relacionados con la compañía: procesos de ingesta, ETL/ELT, limpieza, transformación y carga hacia sistemas analíticos o de producción.

Cada subcarpeta o archivo dentro de `data/pipelines/` debe representar **un pipeline o conjunto de jobs** (por ejemplo `sales-etl`, `telemetry-stream`, `customer-segmentation`) e incluir la configuración necesaria (scripts, orquestación, conectores, esquemas, etc.).

- **Propósito principal**: unificar en un único lugar la lógica de movimiento y transformación de datos que soporta las aplicaciones y analíticas de la compañía.
- **Recomendación**: documenta aquí los pipelines que vayas añadiendo, describiendo su objetivo, orígenes/destinos de datos, dependencias y cómo ejecutarlos en desarrollo, pruebas y producción.

## Pipelines actuales

### Reporte Semanal de Desempeño por Almacén y Cliente (Prefect 3)

- **Punto de entrada:** [`pipeline.py`](./pipeline.py) — flows `weekly-warehouse-client-performance` (ETL completo) y
  `weekly-warehouse-client-performance-preview` (`--dry-run`), y las tasks de cada etapa.
- **Etapas con entrada/salida:** [`weekly_performance/`](./weekly_performance/) (extract, observe, load, snapshot de
  evaluación). **Transformaciones puras:** [`../process/weekly_performance/`](../process/weekly_performance/).
- **Origen → destino:** `telemetry_events` (solo lectura) → `reporting.weekly_warehouse_client_performance` (upsert
  sobre `unique (warehouse, client_id, week_start)`) + `reporting.pipeline_runs` (registro de ejecuciones).
- **Diseño:** [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) (la §18 describe la implementación con Prefect). Operación:
  [`docs/reporting/weekly-performance-pipeline.md`](../../docs/reporting/weekly-performance-pipeline.md).
- **Ejecución** (desde la raíz; Prefect está instalado en el entorno de `services/api`):

  ```powershell
  uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py
  uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py --dry-run
  ```

  Con el entorno virtual de `services/api` activado basta `python data/pipelines/pipeline.py`.
- **Tests:** `services/api/tests/reporting/` (`uv run pytest tests/reporting` desde `services/api`).
