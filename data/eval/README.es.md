# Carpeta `data/eval`

Esta carpeta está orientada a **evaluación y validación**: datasets de evaluación, “golden sets”, resultados de experimentos, métricas, y artefactos usados para medir calidad de modelos, RAG, agentes o pipelines.

- **Propósito principal**: centralizar los insumos y salidas de evaluación para asegurar mejoras medibles a lo largo de los hitos del proyecto.
- **Recomendación**: documenta cada set de evaluación (qué mide, cómo se construyó, criterios de éxito) y evita incluir datos sensibles; si es necesario, usa datos sintéticos o anonimizados.

## Contenido generado (ignorado en git)

- `weekly_performance/` — un snapshot JSON por ejecución del pipeline semanal (`<fecha>_<run_id>.json`): ventana,
  eventos leídos y rechazados por motivo, avisos, cambios por semana, datos de Prefect y las filas publicadas. Lo
  escribe la task opcional `write-eval-snapshot`; si falla, la ejecución queda como parcial. Ruta configurable con
  `PIPELINE_EVAL_DIR`. Sin datos personales.
