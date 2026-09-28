# Despliegue de la API (`services/api`) y conexión del backoffice

Instrucciones para el agente del servidor. Publicar la API permite usar en producción el **analizador de
incidencias** (`/incidencias`) y el **directorio de proveedores** (`/proveedores`) del backoffice, que hoy solo
funcionan en local.

> **Estado: documentado, NO ejecutado.** Todo lo que toca infraestructura, DNS (`rubenlosada.com`), proxy o secretos
> requiere confirmación previa del desarrollador ([`AGENTS.md`](../AGENTS.md) §4). Antes de empezar, el desarrollador
> debe decidir los puntos de [Decisiones pendientes](#decisiones-pendientes).

## Situación actual

| Pieza | Producción hoy |
| --- | --- |
| Backoffice | https://backofficetrackflow.rubenlosada.com/ — Next.js compilado en el servidor desde el tarball de `main` (`npm ci --include=dev` + `npm run build`), detrás de Cloudflare, **sin autenticación** y con `noindex`. |
| API (`services/api`) | No desplegada. Por eso `/proveedores` e `/incidencias` muestran en producción el aviso “Falta la variable NEXT_PUBLIC_API_BASE_URL…”. |

## Decisiones pendientes

1. **Autenticación (bloqueante).** El backoffice no tiene login y la API tampoco. Con la API publicada, cualquiera
   podría subir ficheros, descargar el último resultado agregado y editar tarifas y estados de proveedores. El CSV real
   de incidencias contiene correos de clientes (la API no los devuelve ni los guarda, pero se suben a ella). **Hay que
   proteger backoffice y API antes de publicar**, p. ej. con Cloudflare Access o autenticación básica en el proxy.
2. **Topología** (condiciona cómo se protege):

   | Opción | Cómo | Autenticación | Cambios de código |
   | --- | --- | --- | --- |
   | **A. Subdominio propio** (p. ej. `apitrackflow.rubenlosada.com`) | El navegador llama a otro origen; la API responde con CORS (`CORS_ALLOWED_ORIGINS`). | Delicada: una petición entre orígenes a una API protegida con Cloudflare Access o Basic Auth no envía credenciales por defecto y el preflight `OPTIONS` falla. Exigiría `credentials: "include"` en el backoffice, `allow_credentials` en la API y configurar CORS en Access. | Ninguno sin autenticación; **sí** con autenticación (no probado). |
   | **B. Mismo host** (recomendada si se protege) | El proxy de `backofficetrackflow.rubenlosada.com` envía `/health`, `/suppliers` y `/api/incidents/` a la API local (`127.0.0.1:8000`) y el resto a Next.js. `NEXT_PUBLIC_API_BASE_URL=https://backofficetrackflow.rubenlosada.com`. | Una sola regla (Access o Basic Auth) protege a la vez la página y la API; sin CORS. | Ninguno (no probado en un servidor real; el backoffice no tiene rutas propias con esos prefijos). |

3. **Subdominio** (solo opción A) y su registro DNS en Cloudflare.

## 1. API en producción

Requisitos: Python ≥ 3.12 y [`uv`](https://docs.astral.sh/uv/) (si el sistema no tiene Python 3.12+, `uv` descarga uno
gestionado al sincronizar).

**El tarball debe incluir `services/api` y `packages/analisis-incidencias` respetando sus rutas**: la API declara el
paquete como dependencia local por ruta relativa (`../../packages/analisis-incidencias`). Sin él, `uv sync` falla con
`Distribution not found at: …/packages/analisis-incidencias` (comprobado).

Ejemplo en Linux (rutas orientativas; el nombre de la carpeta raíz del tarball de `codeload` es
`company-rubenlosada-main/`):

```bash
curl -L https://codeload.github.com/rubenlosada11/company-rubenlosada/tar.gz/main -o /tmp/trackflow.tar.gz
mkdir -p /srv/trackflow-api
tar -xzf /tmp/trackflow.tar.gz -C /srv/trackflow-api --strip-components=1 \
  company-rubenlosada-main/services/api company-rubenlosada-main/packages/analisis-incidencias
cd /srv/trackflow-api/services/api
uv sync --locked --no-dev
```

- `--locked`: instala exactamente `uv.lock` (falla si no coincide con `pyproject.toml`). `--no-dev`: sin pytest ni
  httpx2.
- **Datos de proveedores:** TinyDB guarda por defecto en `services/api/db/suppliers.json`, que no está en git. Para
  que una nueva extracción no pueda borrarlo, usar una ruta fuera del código con `SUPPLIERS_DB_PATH` (p. ej.
  `/var/lib/trackflow-api/suppliers.json`). La primera vez, cargar los 15 proveedores iniciales con la API parada:
  `SUPPLIERS_DB_PATH=/var/lib/trackflow-api/suppliers.json uv run --no-sync seed` (idempotente).

Arranque, **con un solo worker**:

```bash
uv run --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

El último análisis de incidencias vive **en memoria del proceso** (`app.state`): con varios workers, la exportación
podría llegar a un proceso que no hizo el análisis y devolver 404. `--no-sync` evita que `uv run` vuelva a instalar las
dependencias de desarrollo. La API escucha solo en `127.0.0.1`: se publica a través del proxy.

Ejemplo de servicio `systemd` (orientativo):

```ini
[Unit]
Description=TrackFlow API (services/api)
After=network.target

[Service]
WorkingDirectory=/srv/trackflow-api/services/api
Environment=CORS_ALLOWED_ORIGINS=https://backofficetrackflow.rubenlosada.com
Environment=SUPPLIERS_DB_PATH=/var/lib/trackflow-api/suppliers.json
ExecStart=/usr/local/bin/uv run --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 2. Variables

| Dónde | Variable | Valor | Cuándo |
| --- | --- | --- | --- |
| API | `CORS_ALLOWED_ORIGINS` | `https://backofficetrackflow.rubenlosada.com` | Al arrancar. Necesaria en la opción A; inocua en la B. Sin ella, el valor por defecto solo admite `localhost:3002`. |
| API | `SUPPLIERS_DB_PATH` | ruta persistente fuera del código | Al arrancar y al ejecutar `seed`. |
| Backoffice | `NEXT_PUBLIC_API_BASE_URL` | A: `https://<dominio-api>` · B: `https://backofficetrackflow.rubenlosada.com` | **Antes de `npm run build`**: Next.js la incrusta en el JavaScript al compilar; cambiarla después no tiene efecto hasta recompilar. |

Recompilar el backoffice en su carpeta del servidor con la variable (el `.env.local` de desarrollo no está en git):

```bash
npm ci --include=dev
NEXT_PUBLIC_API_BASE_URL=https://<dominio-api> npm run build
```

y reiniciar el proceso que sirve el sitio. Sin barra final en la URL (si la tiene, el backoffice la quita).

## 3. Tamaño de subida

La API rechaza ficheros de más de 5 MB con un 413 JSON propio. El proxy debe aceptar **algo más de 5 MB** (el cuerpo
`multipart` añade cabeceras) para que el límite lo aplique la API y el backoffice muestre su mensaje:

- **nginx:** `client_max_body_size` es **1 MB por defecto** → `client_max_body_size 6m;` en el `server`/`location`
  de la API.
- **Cloudflare:** el límite de subida del plan (100 MB en Free y Pro) no afecta.

Ejemplo nginx, opción B (mismo host; orientativo):

```nginx
location = /health          { proxy_pass http://127.0.0.1:8000; }
location /suppliers         { proxy_pass http://127.0.0.1:8000; }
location /api/incidents/    { proxy_pass http://127.0.0.1:8000; client_max_body_size 6m; }
# el resto (/, /_next/, /proveedores, /incidencias…) sigue yendo a Next.js
```

## 4. Riesgo que decidir antes de publicar

Ver [Decisiones pendientes](#decisiones-pendientes), punto 1. Resumen: **no exponer la API sin proteger antes backoffice
y API**. Aunque el análisis devuelve solo agregados (sin correos), cualquiera podría subir ficheros, descargar el
último resultado y modificar proveedores. Además, el último análisis es **compartido** por todos los usuarios (un solo
resultado en memoria).

## 5. Afecta también a proveedores

`/proveedores` usa la misma API y la misma variable `NEXT_PUBLIC_API_BASE_URL`: el despliegue sirve para las dos
páginas. Recordar ejecutar el seeder la primera vez (ver sección 1).

## 6. Verificación tras desplegar

1. `curl https://<dominio-api>/health` → `{"status":"ok"}` (opción B: `https://backofficetrackflow.rubenlosada.com/health`).
2. Backoffice de producción → **Análisis de incidencias** → subir `scripts/incidents-trackflow.csv` → 100 procesados,
   95 válidos, 5 inválidos (TRF-000003, 025, 042, 068, 097), categorías 14/38/19/17/7, estados 29/52/14, países 50/45,
   satisfacción 3,06 (6/11/15/14/6), US 2,96 · ES 3,17.
3. **Descargar resultados CSV** → `results.csv` de 5958 bytes, SHA-256
   `f7ee9c99f634abeaf8dc895aa56b67ee5b4e96316329c6603a47798dc373bafa` (el mismo que `python analyze.py` exporta en
   local). En PowerShell: `Get-FileHash .\results.csv`.
4. `/proveedores` muestra los 15 proveedores y deja cambiar una tarifa.
5. Log de la API: una línea `trackflow.api.incidents: Análisis de 'incidents-trackflow.csv': 100 registros …` por
   análisis, sin correos ni trazas.
6. Si se protegió: sin sesión, backoffice y API deben pedir autenticación.

## Comprobado en local (2026-09-28)

Simulación del despliegue de la API a partir de un `git archive` de la rama con solo `services/api` y
`packages/analisis-incidencias`: `uv sync --locked --no-dev` (sin pytest ni httpx2), `uv run --no-sync seed` (15/0/15)
y `uvicorn … --workers 1` con `CORS_ALLOWED_ORIGINS=https://backofficetrackflow.rubenlosada.com` → `/health` 200,
15 proveedores, análisis 100/95/5 (media 3.06), exportación idéntica a la del script (SHA-256 anterior), CORS permitido
para el origen de producción y rechazado para `localhost:3002`, `Access-Control-Expose-Headers: Content-Disposition`,
log sin correos. Sin el paquete, `uv sync` falla (exit 2). **No probado:** proxy, Cloudflare, autenticación ni la
opción B en un servidor real.
