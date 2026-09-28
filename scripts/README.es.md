# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

## Analizador de incidencias

CLI del analizador del CSV de incidencias de CX ([`CONTEXT-incidencias.es.md`](../CONTEXT-incidencias.es.md)). La
validación, las métricas y la exportación viven en [`packages/analisis-incidencias`](../packages/analisis-incidencias/README.md),
que el script importa desde `src/` sin instalarlo. Solo necesita Python ≥ 3.11 (biblioteca estándar).

| Fichero | Qué es |
| --- | --- |
| [`analyze.py`](./analyze.py) | Informe en consola y exportación opcional a `results.csv` (una fila por métrica) |
| [`incidents-trackflow.csv`](./incidents-trackflow.csv) | CSV de prueba del ejercicio (100 filas; datos ficticios) |
| [`tests/`](./tests/) | Tests de la CLI y del contrato con los valores esperados del CONTEXT |

En Windows PowerShell, desde la raíz del repo (un comando por línea):

```powershell
cd scripts
python analyze.py incidents-trackflow.csv
```

- Al terminar pregunta `¿Deseas exportar los resultados a CSV? [s / n]` (acepta `s`, `sí`, `si`, `y`, `n`, `no`; con
  Ctrl+C o fin de entrada termina sin exportar). `-o/--output` cambia el fichero de destino; `scripts/results.csv`
  está en `.gitignore`.
- Códigos de salida: `0` correcto, `1` error de fichero, `2` falta el argumento.
- Nunca muestra ni exporta `customer_email`: los inválidos se identifican por línea e `incident_id`.

Tests, desde la raíz del repo: `python -m pytest scripts/tests packages/analisis-incidencias/tests`.
