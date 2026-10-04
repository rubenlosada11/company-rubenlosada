# analisis-incidencias

Lógica compartida del **Analizador de Incidencias** de TrackFlow: carga del CSV, validación de registros según
[`CONTEXT-incidencias.es.md`](../../CONTEXT-incidencias.es.md), cálculo de métricas y exportación a CSV.

La usan dos consumidores, sin duplicar código:

- `scripts/analyze.py` (CLI): la importa directamente desde `src/`, sin instalación.
- `services/api` (FastAPI): la declara como dependencia local.
- `scripts/seed_incidents.py`: valida el CSV histórico y lo transforma para el gestor de incidencias.

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
| `gestor.py` | **Gestor de incidencias** ([`CONTEXT-gestor-incidencias.es.md`](../../CONTEXT-gestor-incidencias.es.md)): sedes, categorías, estados y orígenes; `validar_campo` / `validar_incidencia` (mensajes en español); `transicion_permitida` / `validar_transicion`; mapeos del CSV y `transformar_fila` |

## Uso

```python
from analisis_incidencias import analizar, decodificar_csv, generar_csv_bytes

resultado = analizar(decodificar_csv(contenido_bytes), "incidents-trackflow.csv")
csv_bytes = generar_csv_bytes(resultado)
```

El gestor de incidencias usa nombres de campo y valores distintos a los del CSV, así que su módulo se importa
aparte:

```python
from analisis_incidencias import gestor, validar_registro

if not validar_registro(fila.datos, fila.columnas_ok):   # fila válida para el analizador
    incidencia = gestor.transformar_fila(fila.datos)     # CSV → campos del modelo Incident
    errores = gestor.validar_incidencia(incidencia)      # {} si es válida
gestor.validar_transicion("resolved", "open")            # motivo del rechazo, o None
```

## Tests

Desde la raíz del repositorio:

```
python -m pytest packages/analisis-incidencias/tests
```
