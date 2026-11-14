"""Transformaciones del Reporte Semanal de Desempeño por Almacén y Cliente (PIPELINE_DESIGN.md §6).

- `events`: los cuatro `event_type` de origen y las columnas que entrega la extracción.
- `validate`: reglas de calidad (rechaza y cuenta, nunca corrige).
- `kpis`: una función por KPI del BRIEFING (Volumen de entrada, Throughput de salida, Frecuencia de quiebre de stock,
  Tasa de discrepancia) y `build_rows`; son el cuerpo de las tasks de KPI del Hito 6.
- `aggregate`: semana ISO de cada evento y filas por `(warehouse, client_id, week_start)` (encadena `kpis`).
- `transform`: validate → aggregate → controles de coherencia, más la huella de los datos de entrada y la versión del
  código que usa la caché de Prefect.

Sin dependencias de la API, de la base de datos ni de Prefect: se prueban con DataFrames construidos a mano.
"""
