# Mediciones de la optimización de caché

Scripts y resultados de la optimización de rendimiento con caché (backend) y carga diferida y `useMemo` (backoffice).
Análisis, decisiones y conclusiones en [`../../CACHING_REPORT.md`](../../CACHING_REPORT.md).

```text
audit/caching/
├── seed_benchmark.py      # dataset sintético y reproducible, siempre en un directorio nuevo
├── bench_api.py           # prueba de carga de los endpoints de lectura (cliente + log de tiempos del servidor)
├── workload.py            # carga mixta de lecturas y escrituras: aciertos, fallos e invalidaciones de la caché
├── measure_frontend.mjs   # JS por ruta, carga bajo demanda y tiempo por pulsación en el navegador (Edge)
└── results/
    ├── before.json · after.json                    # bench_api.py sin caché / con caché
    ├── workload.json                               # workload.py
    └── frontend-before.json · frontend-after.json  # measure_frontend.mjs
```

Ningún script forma parte de una app ni toca las bases reales: `seed_benchmark.py` y `workload.py` se niegan a
usar `services/api/db/`, y la API de las mediciones se arranca con `SUPPLIERS_DB_PATH`, `INCIDENTS_DB_PATH`,
`AUTH_DB_PATH` y `DATABASE_URL` apuntando a **copias** del dataset (un SQLite copiado; nunca Supabase).

## Condiciones

| Pieza | Valor |
| --- | --- |
| Equipo | Windows 11, Python 3.14.6, Node 24.19, un solo proceso de uvicorn (sin `--reload`, `--no-access-log`) |
| Dataset | `seed_benchmark.py` con los valores por defecto: 500 proveedores, 5.000 incidencias, 1.000 SKUs, 20.000 entradas y 13.403 salidas (semilla `20261102`) |
| Carga | 10 peticiones de calentamiento + 200 medidas por endpoint, secuenciales y con los mismos parámetros, sobre una conexión persistente; `/inventory/orders` (> 1 s por petición), 2 + 20. Después, las mismas peticiones con 8 hilos |
| «Antes» | El código de la rama con el middleware de tiempos, pero sin caché (copia del paquete `app/` con las rutas y servicios de `main`) |
| Frontend | `next build --webpack` + `next start -p 3002` (Turbopack no compila en este equipo por Google Fonts, también en `main`), Microsoft Edge 156 sin interfaz con `playwright-core`, prefetch del router bloqueado para medir solo cada ruta |

## Repetir la medición (PowerShell, desde la raíz del repo)

Herramientas fuera del repo: `playwright-core` instalado en una carpeta propia (`npm install playwright-core`).

```powershell
uv run --project services/api python audit/caching/seed_benchmark.py $env:TEMP\bench-data --password <contraseña>
Copy-Item -Recurse $env:TEMP\bench-data $env:TEMP\bench-run
$env:SECRET_KEY = "<clave de al menos 32 caracteres>"
$env:SUPPLIERS_DB_PATH = "$env:TEMP\bench-run\suppliers.json"
$env:INCIDENTS_DB_PATH = "$env:TEMP\bench-run\incidents.json"
$env:AUTH_DB_PATH = "$env:TEMP\bench-run\auth.json"
$env:DATABASE_URL = "sqlite:///$($env:TEMP -replace '\\','/')/bench-run/inventory.db"
cd services\api
uv run uvicorn app.main:app --port 8031 --no-access-log *> $env:TEMP\server.log
```

En otra terminal:

```powershell
python audit/caching/bench_api.py --base-url http://127.0.0.1:8031 --email benchmark@trackflow.test --password <contraseña> --concurrency 8 --server-log $env:TEMP\server.log --out audit/caching/results/after.json
Copy-Item -Recurse $env:TEMP\bench-data $env:TEMP\bench-workload
uv run --project services/api python audit/caching/workload.py $env:TEMP\bench-workload --out audit/caching/results/workload.json
```

Backoffice (con la API anterior arrancada; `NEXT_PUBLIC_*` se incrustan al compilar):

```powershell
cd uis\backoffice
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8031"
$env:NEXT_PUBLIC_INVENTORY_API_URL = "http://localhost:8031"
npx next build --webpack
node node_modules/next/dist/bin/next start -p 3002
```

```powershell
node audit/caching/measure_frontend.mjs --playwright <carpeta de playwright-core> --email benchmark@trackflow.test --password <contraseña> --out audit/caching/results/frontend-after.json
```

Después, vuelve a compilar el backoffice sin esas variables (`npm run build`) para que use tu `.env.local`.
