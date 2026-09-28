# analisis-incidencias

Lógica compartida del **Analizador de Incidencias** de TrackFlow: carga del CSV, validación de registros según
[`CONTEXT-incidencias.es.md`](../../CONTEXT-incidencias.es.md), cálculo de métricas y exportación a CSV.

La usan dos consumidores, sin duplicar código:

- `scripts/analyze.py` (CLI): la importa directamente desde `src/`, sin instalación.
- `services/api` (FastAPI): la declara como dependencia local.

Solo usa la biblioteca estándar de Python (≥ 3.11) y procesa los datos en local. El resultado de `analizar()` no
contiene correos ni otros datos personales.

## Módulos

| Módulo | Responsabilidad |
| --- | --- |
| `dominio.py` | Campos, países, transportistas, categorías, estados y reglas del CONTEXT |
| `carga.py` | `leer_csv`, `decodificar_csv`, `parsear_csv` y `ErrorAnalisis` (errores de fichero) |
| `validacion.py` | `validar_registro`: códigos de las reglas que incumple un registro |
| `metricas.py` | `analizar`: separa válidos/inválidos y calcula las métricas (dict serializable a JSON) |
| `exportacion.py` | `generar_csv` / `generar_csv_bytes`: una fila por métrica (`seccion,metrica,valor,porcentaje`) |

## Uso

```python
from analisis_incidencias import analizar, decodificar_csv, generar_csv_bytes

resultado = analizar(decodificar_csv(contenido_bytes), "incidents-trackflow.csv")
csv_bytes = generar_csv_bytes(resultado)
```

## Tests

Desde la raíz del repositorio:

```
python -m pytest packages/analisis-incidencias/tests
```
