"""Transformaciones del Reporte Semanal de Desempeño por Almacén y Cliente (PIPELINE_DESIGN.md §6).

- `events`: los cuatro `event_type` de origen y las columnas que entrega la extracción.
- `validate`: reglas de calidad (rechaza y cuenta, nunca corrige).
- `aggregate`: KPIs por `(warehouse, client_id, week_start)`.
- `transform`: validate → aggregate → controles de coherencia, más la huella de los datos de entrada y la versión del
  código que usa la caché de Prefect.

Sin dependencias de la API, de la base de datos ni de Prefect: se prueban con DataFrames construidos a mano.
"""
