"""Código de datos de TrackFlow importable desde la raíz del monorepo (`data.pipelines`, `data.process`).

- `data/pipelines/`: pipelines orquestados con Prefect 3 (punto de entrada `data/pipelines/pipeline.py`).
- `data/process/`: transformaciones reutilizables, puras (Pandas, sin base de datos ni Prefect).
- `data/raw/` y `data/eval/`: ficheros intermedios y resultados de evaluación que generan los pipelines (ignorados en
  git); solo se versionan sus README.
"""
