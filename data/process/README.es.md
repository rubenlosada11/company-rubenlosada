# Carpeta `data/process`

Esta carpeta contiene **datos procesados/intermedios** y/o artefactos derivados de los pipelines (por ejemplo: datasets limpios, features, agregados, tablas intermedias o resultados de transformaciones).

- **Propósito principal**: separar claramente los datos “raw” de los datos listos para análisis/modelado/consumo por apps.
- **Recomendación**: documenta qué pipeline genera cada artefacto, su esquema, periodicidad, y cómo se valida su calidad (checks, constraints, tests de datos).

## Contenido actual

- [`weekly_performance/`](./weekly_performance/) — **transformaciones reutilizables** del Reporte Semanal de Desempeño
  (código, no datos): reglas de calidad (`validate`), KPIs por almacén, cliente y semana ISO (`aggregate`) y la
  transformación completa con controles de coherencia, huella de los datos y versión del código para la caché de
  Prefect (`transform`). Funciones puras sobre DataFrames: sin base de datos ni Prefect. Las usa
  [`data/pipelines/pipeline.py`](../pipelines/pipeline.py).
