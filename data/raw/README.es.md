# Carpeta `data/raw`

Esta carpeta está pensada para almacenar **datos en bruto** (raw) relacionados con la compañía: dumps, exports, archivos de ejemplo, muestras de eventos, o datasets sin transformar.

- **Propósito principal**: servir como zona de aterrizaje o referencia de datos originales antes de ser procesados por pipelines.
- **Recomendación**: documenta el origen de cada dataset, formato, tamaño esperado, consideraciones de privacidad/PII y cómo se versiona (idealmente evitando subir datos sensibles al repositorio).

## Contenido generado (ignorado en git)

- `prefect-results/` — resultados cacheados de la task `transform-weekly-kpis` del pipeline semanal
  ([`data/pipelines/pipeline.py`](../pipelines/pipeline.py)): ficheros intermedios con caducidad de 1 día. Se pueden
  borrar en cualquier momento (la siguiente ejecución recalcula). Ruta configurable con
  `PREFECT_RESULTS_LOCAL_STORAGE_PATH`.
