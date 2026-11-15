"""Procesos en segundo plano (DEV-53): registro de ejecuciones en `job_runs` (`job_runner`).

La API **no** importa este paquete: lo usan los procesos independientes de `scripts/` (p. ej.
`scripts/nightly_export.py`), que reutilizan la conexión de `app.database`. Documentación:
docs/telemetry/nightly-export.md.
"""
