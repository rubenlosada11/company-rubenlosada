# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

> _Spanish version: [README.es.md](./README.es.md)._

## Current pipelines

- **Weekly warehouse/client performance report (Prefect 3)** — entry point [`pipeline.py`](./pipeline.py) (flows and
  tasks), I/O stages in [`weekly_performance/`](./weekly_performance/), pure transformations in
  [`../process/weekly_performance/`](../process/weekly_performance/). `telemetry_events` (read only) →
  `reporting.weekly_warehouse_client_performance` + `reporting.pipeline_runs`. Design (in Spanish):
  [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md). Run from the repo root:
  `uv run --project services/api --env-file services/api/.env python data/pipelines/pipeline.py` (or
  `python data/pipelines/pipeline.py` with the `services/api` virtual environment active).
