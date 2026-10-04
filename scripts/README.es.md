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
- Códigos de salida: `0` correcto, `1` error (fichero que no existe o no se puede leer, CSV no procesable, fallo al
  escribir la exportación o error imprevisto), `2` falta el argumento. Los errores se escriben en stderr, sin trazas.
- Nunca muestra ni exporta `customer_email`: los inválidos se identifican por línea e `incident_id`.

Tests, desde la raíz del repo: `python -m pytest scripts/tests packages/analisis-incidencias/tests`. Documentación
completa (API, backoffice, reglas y decisiones): [`docs/analizador-incidencias.md`](../docs/analizador-incidencias.md).
Captura de la salida en consola (tres partes): [1](./screenshots/screenshot%20script%20consola1.png),
[2](./screenshots/screenshot%20script%20consola2.png) y [3](./screenshots/screenshot%20script%20consola3.png).

## Seed del gestor de incidencias

[`seed_incidents.py`](./seed_incidents.py) carga el CSV histórico [`incidents-trackflow.csv`](./incidents-trackflow.csv)
en la base del gestor de incidencias (`services/api/db/incidents.json`), con los mapeos de
[`CONTEXT-gestor-incidencias.es.md`](../CONTEXT-gestor-incidencias.es.md). Valida cada fila con la misma lógica que el
analizador, la pasa por el modelo de la API y descarta e informa de las que no valen.

A diferencia de `analyze.py`, necesita el entorno de la API (TinyDB y los modelos). Desde la **raíz del repo**, con la
API parada:

```powershell
uv run --project services/api python scripts/seed_incidents.py
```

- Resultado con el CSV de prueba: 100 filas leídas, 95 válidas e insertadas, 5 inválidas. Es idempotente: la segunda
  ejecución da 0 insertadas y 95 duplicadas.
- Admite la ruta de otro CSV como argumento. `INCIDENTS_DB_PATH` cambia el fichero de la base.
- Códigos de salida: `0` correcto, `1` error del CSV, de escritura o de la base de datos (fichero ilegible o JSON
  corrupto: indica cuál y por qué), `2` falta el entorno de la API (p. ej. al ejecutarlo con el Python del sistema).
  Los errores se escriben en stderr, sin trazas.
- No imprime ni guarda `customer_email`.

Sus tests están en [`services/api/tests/test_seed_incidents.py`](../services/api/tests/test_seed_incidents.py), porque
necesitan TinyDB (`uv run pytest -q` desde `services\api`). Documentación completa:
[`docs/gestor-incidencias.md`](../docs/gestor-incidencias.md).
