# Docker: desarrollo local y despliegue en el VPS

Infraestructura Docker del monorepo (ticket «Contenedorización del monorepo»). Dos contenedores:

| Servicio | Contenido | Puertos internos | Dockerfile |
| --- | --- | --- | --- |
| `interfaces` | `uis/website` y `uis/backoffice` (dos apps Next.js independientes, un proceso cada una) | website **3000**, backoffice **3001** | [`uis/Dockerfile`](../uis/Dockerfile) + [`uis/start.sh`](../uis/start.sh) |
| `backend` | `services/api` (FastAPI + Uvicorn) y el paquete local `packages/analisis-incidencias` | **8000** | [`services/Dockerfile`](../services/Dockerfile) |

| Fichero | Para qué |
| --- | --- |
| [`docker-compose.yml`](../docker-compose.yml) | Desarrollo: `next dev`, `uvicorn --reload`, código montado (bind mounts) |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | Producción: `next start`, Uvicorn sin `--reload`, imágenes autocontenidas |
| [`.env.example`](../.env.example) → `.env` | Variables de desarrollo (raíz del repo; `.env` ignorado en git) |
| [`env.prod.example`](../env.prod.example) | Plantilla de producción (en el VPS se copia a `.env` y allí se rellenan los secretos) |
| [`uis/.dockerignore`](../uis/.dockerignore), [`services/.dockerignore`](../services/.dockerignore) | Qué no entra en cada imagen |
| [`services/requirements.txt`](../services/requirements.txt) | Dependencias de la API con hashes, **generado desde `services/api/uv.lock`** |

Las apps de hitos anteriores (`landing`, `script-automatizacion`, `talent-pipeline-tracker`) no se contenerizan.
Los ficheros Docker siguen la estructura del ticket (`uis/`, `services/` y la raíz) en lugar de `infra/`.

## 1. Requisitos previos

- **Docker Desktop** (Windows/macOS) o Docker Engine + plugin Compose V2 (Linux). Comprobado con Docker 29.7 /
  Compose 5.5 en Windows 11 (WSL2) y Docker 29.9 / Compose 5.6 en Ubuntu 22.04.
- Unos **3 GB de RAM libres** para el entorno de desarrollo (`next dev` de las dos apps ronda 1,2 GB).
- Para desplegar: acceso SSH al VPS (alias `bc-vps-248` en `~/.ssh/config`).
- No hace falta Node, Python ni uv en el equipo para usar Docker (sí para trabajar sin Docker, ver los README).

## 2. Instalar Docker

- **Windows:** instala [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) con el
  backend WSL2 y ábrelo antes de usar `docker` (si no, `failed to connect to the docker API … dockerDesktopLinuxEngine`).
- **Linux (Ubuntu):** repositorio oficial de Docker
  ([guía](https://docs.docker.com/engine/install/ubuntu/)): paquetes `docker-ce docker-ce-cli containerd.io
  docker-buildx-plugin docker-compose-plugin`. Es lo que se instaló en el VPS.

Comprobación: `docker --version` y `docker compose version` (debe ser Compose V2: `docker compose`, sin guion).

## 3. Configuración inicial (desarrollo)

Desde la raíz del repo, en PowerShell (un comando por línea):

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Pega la clave generada en `SECRET_KEY=` dentro de `.env`. Con `change-me` o vacía la API no arranca a propósito
(el mensaje habla de `services/api/.env`, que es el `.env` para trabajar **sin** Docker; con Docker es el de la raíz).

## 4. Variables de entorno

Un único `.env` en la raíz para Docker. Los `.env` propios de cada app (`services/api/.env`,
`uis/backoffice/.env.local`) siguen sirviendo para trabajar sin Docker y Docker no los lee.

| Variable | Tipo | Desarrollo (`.env`) | Producción (`.env` del VPS) |
| --- | --- | --- | --- |
| `WEBSITE_PORT`, `BACKOFFICE_PORT`, `API_PORT` | pública | Puertos de tu equipo (3000, 3001, 8000) | Puertos en `127.0.0.1` del VPS (por defecto 3000, 3001, 8000) |
| `NEXT_PUBLIC_API_BASE_URL` | pública, **se incrusta en el bundle** | Calculada: `http://localhost:${API_PORT}` | `http://localhost:18000` (túnel SSH); se usa al **compilar** la imagen |
| `NEXT_PUBLIC_INVENTORY_API_URL` | pública | Vacía = misma API | Vacía |
| `CORS_ALLOWED_ORIGINS`, `FRONTEND_BASE_URL` | pública | Calculadas a partir de `BACKOFFICE_PORT` | `http://localhost:13001` (túnel SSH) |
| `NEXT_DEV_BUNDLER`, `WATCHPACK_POLLING` | pública | Por defecto `webpack` y `true` (ver «Hot reload») | — |
| `IMAGE_TAG` | pública | — | Etiqueta de las imágenes desplegadas |
| `SECRET_KEY` | **secreta** | Generada por ti | Generada en el VPS |
| `REGISTRATION_CODE` | **secreta** | Vacía = registro abierto | Generada en el VPS (registro solo con código) |
| `RESEND_API_KEY`, `MAIL_FROM` | **secreta** | Vacías = sin emails | Vacías salvo que se decida lo contrario |
| `DATABASE_URL` | **secreta** | Comentada = SQLite en `services/api/db` | Comentada = SQLite en el volumen; o un proyecto Supabase existente |

Reglas: las `NEXT_PUBLIC_*` son visibles en el navegador (nunca secretos). Los secretos solo llegan al contenedor
`backend` (`env_file`); `interfaces` no los recibe. El `.env` real nunca se sube a git (`.gitignore`: `.env`,
`.env.*`, salvo la plantilla `.env.example`). La plantilla de producción se llama `env.prod.example`, sin punto
inicial, porque el protocolo del repo (`AGENTS.md`) solo permite versionar `.env.example`.

## 5. Ejecución local

```powershell
docker compose up
```

La primera vez construye las imágenes (≈ 1,5 min sin caché) y arranca primero `backend` y, cuando está sano,
`interfaces`. Otras órdenes habituales:

```powershell
docker compose up -d
docker compose ps
docker compose logs -f
docker compose logs -f interfaces
docker compose down
```

- `up -d`: en segundo plano. `down`: para y borra los contenedores y la red (los datos de `services/api/db` están en
  tu disco y no se pierden).
- Scripts de la API dentro del contenedor:
  `docker compose exec backend python -m app.seed` · `docker compose exec backend python -m app.seed_inventory` ·
  `docker compose exec backend python -m app.create_admin <email>` (pide la contraseña).
- En desarrollo la API usa **los mismos datos** que sin Docker (`services/api/db`, montado). No arranques a la vez
  `uv run uvicorn` en el puerto 8000 ni `npm run dev` del website (usa el 3001, el mismo que el backoffice en Docker).

## 6. Puertos

| URL (desarrollo) | Servicio |
| --- | --- |
| http://localhost:3000 | Website |
| http://localhost:3001 | Backoffice (`/login`) |
| http://localhost:8000 | API (`/health`, `/docs`) |

Solo escuchan en `127.0.0.1`: no se exponen a tu red local. Para cambiarlos, edita `WEBSITE_PORT`,
`BACKOFFICE_PORT` o `API_PORT` en `.env`; CORS y la URL de la API se recalculan solos.

## 7. Arquitectura Docker

```text
DESARROLLO (tu equipo)                          PRODUCCIÓN (VPS, sin acceso público)

navegador ─► localhost:3000  website             tu equipo: ssh -L 13000/13001/18000 ─► 127.0.0.1:3000/3001/8000
          ─► localhost:3001  backoffice                              │
          ─► localhost:8000  API (CORS)          ┌──────── red trackflow-prod-net ───────────────┐
                                                 │ interfaces (next start ×2)  backend (uvicorn)  │
┌──────────── red trackflow-net ──────────┐      │                    volumen trackflow-api-data  │
│ interfaces (next dev ×2)                 │      └────────────────────────────────────────────────┘
│     └─ depends_on / http://backend:8000 ─┼─► backend (uvicorn --reload)
└──────────────────────────────────────────┘
```

- **`interfaces`** (`node:24.19.0-alpine3.24`): cada app instala sus dependencias con su propio `package-lock.json`
  (`npm ci`). `tini` es el PID 1 y [`start.sh`](../uis/start.sh) lanza las dos apps, pone el prefijo `[website]` /
  `[backoffice]` a sus logs, reenvía `SIGTERM`/`SIGINT` y, si una app termina sola, para la otra y sale con error
  (Docker la reinicia en producción). Usuario sin privilegios `node`.
- **`backend`** (`python:3.13.18-slim-trixie` + uv 0.12.19): `uv pip install --require-hashes -r requirements.txt`.
  La API **no se instala como paquete**: busca sus bases junto al código (`<código>/db`), así que se ejecuta desde
  `/app/services/api` con `PYTHONPATH`. Usuario sin privilegios `trackflow` (uid 1000); solo escribe en `db/`.
  Producción: **un solo worker** (la API guarda el último análisis en memoria y usa candados de hilo).

| | Desarrollo | Producción |
| --- | --- | --- |
| Proyecto / red | `trackflow` / `trackflow-net` | `trackflow-prod` / `trackflow-prod-net` |
| Frontend | `next dev` (webpack con sondeo) | `next build` en la imagen + `next start` |
| API | `uvicorn --reload` | `uvicorn --workers 1` |
| Código | Bind mounts | Dentro de la imagen; API con sistema de ficheros de solo lectura |
| Datos de la API | `services/api/db` del host | Volumen `trackflow-api-data` |
| Reinicio | Manual | `restart: unless-stopped` |
| Límites | — | 512 MB `interfaces`, 256 MB `backend`; logs rotados (3 × 10 MB) |
| Endurecimiento | Usuarios sin privilegios | Además `cap_drop: ALL` y `no-new-privileges` |

## 8. Comunicación entre servicios

| Flujo | Cómo |
| --- | --- |
| Navegador → website / backoffice | `localhost:3000` / `localhost:3001` (o el túnel en producción) |
| Navegador → API | El backoffice llama a la API **desde el navegador** con `NEXT_PUBLIC_API_BASE_URL`. Debe ser una URL que resuelva el navegador (`localhost`), **nunca `backend`**: el navegador no conoce los nombres de Docker. La API lo permite con CORS (`CORS_ALLOWED_ORIGINS`). |
| Contenedor → contenedor | Por nombre de servicio en la red de Compose: `http://backend:8000` (por ejemplo `docker compose exec interfaces wget -qO- http://backend:8000/health`). Hoy ninguna app hace llamadas de servidor a la API; el nombre se usa en `depends_on` y en las comprobaciones. |

La autenticación es JWT Bearer guardado en `localStorage` (sin cookies): funciona entre orígenes sin configuración
extra de cookies.

## 9. Hot reload

| App | Mecanismo | Tiempo medido |
| --- | --- | --- |
| Website y backoffice | `next dev --webpack` con `WATCHPACK_POLLING=true` | ≈ 2–5 s tras guardar |
| API | `uvicorn --reload` (StatReload, por sondeo) vigilando `app/` y el paquete local | ≈ 4 s |

Docker Desktop en Windows **no propaga los eventos de ficheros** de los bind mounts: Turbopack (por defecto en
Next 16) no ve los cambios (comprobado), por eso Docker usa webpack con sondeo. En Linux/macOS puedes volver a
Turbopack con `NEXT_DEV_BUNDLER=turbopack` en `.env`. Fuera de Docker (`npm run dev`) y en producción sigue Turbopack.

## 10. Reconstruir imágenes

```powershell
docker compose build
docker compose up --build
docker compose up --build --renew-anon-volumes
```

- Tras cambiar un `Dockerfile`, `start.sh` o `services/requirements.txt`: `docker compose up --build`.
- Tras cambiar un **`package-lock.json`**: añade `--renew-anon-volumes`; `node_modules` vive en volúmenes anónimos
  que, si no, conservan las dependencias antiguas.
- Tras cambiar las dependencias de la API (`uv add …`), regenera `requirements.txt` desde `services\api` y reconstruye:

```powershell
cd services\api
uv export --frozen --format requirements.txt --no-dev --no-emit-project --no-emit-package analisis-incidencias --output-file ../requirements.txt
```

## 11. Logs

```powershell
docker compose logs -f
docker compose logs -f backend
docker compose logs --tail 100 interfaces
```

En producción, lo mismo con `-f docker-compose.prod.yml` (rotados: 3 ficheros de 10 MB por contenedor).

## 12. Parar los contenedores

```powershell
docker compose stop
docker compose down
```

`stop` los detiene sin borrarlos; `down` los borra junto con la red. `down -v` borra también los volúmenes anónimos
(`node_modules`, `.next`) y obliga a reinstalar al volver a arrancar; los datos de la API no se ven afectados en
desarrollo. **En producción nunca uses `down -v`**: borraría el volumen `trackflow-api-data`.

## 13. Configuración de producción

[`docker-compose.prod.yml`](../docker-compose.prod.yml): imágenes de la etapa `prod`, sin código montado, sin
`next dev` ni `--reload`, `restart: unless-stopped`, healthchecks, límites de memoria, logs rotados, puertos solo en
`127.0.0.1` y `pull_policy: never` (las imágenes se cargan con `docker load`, nunca se descargan de un registro).

**Las imágenes se compilan en tu equipo**: el VPS tiene ~1 GB de RAM y compilar Next.js allí podría dejarlo sin
memoria. `NEXT_PUBLIC_API_BASE_URL` se incrusta al compilar, por eso se lee de `env.prod.example` (sin secretos).

## 14. Despliegue en el VPS

Estado actual: desplegado en `bc-vps-248`, carpeta **`/opt/company-rubenlosada/`** (contiene solo
`docker-compose.prod.yml`, `.env` con permisos 600 y `env.prod.example`). **Sin acceso público**: no hay dominio,
proxy ni HTTPS, y los puertos solo escuchan en `127.0.0.1` del VPS.

### Primer despliegue (ya hecho; referencia)

1. Docker Engine + Compose desde el repositorio oficial (sección 2).
2. Compilar y enviar las imágenes (pasos 1–3 de «Actualizar producción»).
3. Copiar los ficheros y crear el `.env` **en el VPS**, generando allí los secretos:

```powershell
ssh bc-vps-248 "install -d -m 0750 /opt/company-rubenlosada"
scp docker-compose.prod.yml env.prod.example bc-vps-248:/opt/company-rubenlosada/
ssh bc-vps-248
```

Ya en el VPS (bash):

```bash
cd /opt/company-rubenlosada
umask 077 && cp env.prod.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → REGISTRATION_CODE
nano .env                                                       # IMAGE_TAG, SECRET_KEY, REGISTRATION_CODE
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --no-build
docker compose -f docker-compose.prod.yml exec backend python -m app.seed
```

4. Crear el primer administrador (pendiente: lo hace el desarrollador, porque pide la contraseña; `ssh -t` da la terminal que necesita):

```powershell
ssh -t bc-vps-248 "cd /opt/company-rubenlosada && docker compose -f docker-compose.prod.yml exec backend python -m app.create_admin tu-email@dominio"
```

### Acceder a producción (túnel SSH)

```powershell
ssh -N -L 13000:127.0.0.1:3000 -L 13001:127.0.0.1:3001 -L 18000:127.0.0.1:8000 bc-vps-248
```

Con el túnel abierto: website http://localhost:13000, backoffice http://localhost:13001, API
http://localhost:18000/docs. Los puertos 13000/13001/18000 no chocan con el entorno de desarrollo. Para registrarse
hace falta el `REGISTRATION_CODE` del `.env` del VPS (`ssh bc-vps-248 "grep REGISTRATION_CODE /opt/company-rubenlosada/.env"`).

### Equivalentes de producción

En el VPS, desde `/opt/company-rubenlosada`:

```bash
docker compose -f docker-compose.prod.yml up -d --no-build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml restart
docker compose -f docker-compose.prod.yml down
```

En tu equipo (solo compilar):

```powershell
docker compose -f docker-compose.prod.yml --env-file env.prod.example build
```

## 15. Actualizar producción

En tu equipo, desde la raíz del repo (PowerShell; usa la tubería de `cmd`, porque PowerShell 5.1 corrompe los
datos binarios en sus propias tuberías):

```powershell
$env:IMAGE_TAG = git rev-parse --short HEAD
docker compose -f docker-compose.prod.yml --env-file env.prod.example build
cmd /c "docker save trackflow-interfaces:%IMAGE_TAG% trackflow-backend:%IMAGE_TAG% | ssh -C bc-vps-248 docker load"
scp docker-compose.prod.yml bc-vps-248:/opt/company-rubenlosada/
```

(La transferencia tarda ≈ 1,5–2 min; solo hace falta copiar el Compose si ha cambiado.) Después, en el VPS:

```bash
cd /opt/company-rubenlosada
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=<nueva-etiqueta>/" .env
docker compose -f docker-compose.prod.yml up -d --no-build
docker compose -f docker-compose.prod.yml ps
```

Compose recrea solo los contenedores cuya imagen cambió; el volumen de datos se conserva. Convención de etiquetas:
el hash corto del commit desplegado (el primer despliegue, hecho antes de los commits, usa `infra40-rc1`).

## 16. Volver a la versión anterior

Las imágenes anteriores siguen cargadas en el VPS (`docker image ls trackflow-*`). Para volver:

```bash
cd /opt/company-rubenlosada
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=<etiqueta-anterior>/" .env
docker compose -f docker-compose.prod.yml up -d --no-build
```

No borra volúmenes ni toca otros proyectos (comprobado con una etiqueta de prueba). Para liberar disco, borra solo
etiquetas concretas de TrackFlow que ya no uses: `docker image rm trackflow-interfaces:<etiqueta> trackflow-backend:<etiqueta>`.
**Nunca** `docker system prune` ni `docker volume prune` en el VPS (es compartido). Para retirar el stack sin perder
datos: `docker compose -f docker-compose.prod.yml down` (sin `-v`).

## 17. Problemas habituales

| Síntoma | Causa y solución |
| --- | --- |
| `failed to connect to the docker API … dockerDesktopLinuxEngine` | Docker Desktop está cerrado: ábrelo y espera a que diga *Engine running*. |
| `env file …\.env not found` | Falta el `.env` de la raíz: `Copy-Item .env.example .env` y rellena `SECRET_KEY`. |
| `backend` no pasa a *healthy*; log `La API no puede arrancar: SECRET_KEY …` | `SECRET_KEY` vacía, corta o `change-me` en el `.env` de la raíz. |
| `Bind for 127.0.0.1:3001 failed: port is already allocated` | Otro proceso usa el puerto (p. ej. `npm run dev` del website o tu API local): páralo o cambia el puerto en `.env`. |
| `docker compose ps` dice *healthy* pero `localhost:3001` devuelve otra app o un 404 (p. ej. «Página no encontrada \| TrackFlow» en `/login`) | Otro proceso (`npm run dev`/`next start` del website, que usa el 3001) escucha en `0.0.0.0`/`[::]`; Docker publica en `127.0.0.1` y Windows deja que convivan **sin avisar**. `localhost` resuelve antes a `::1` y llega al otro proceso (comprobado: `127.0.0.1:3001` → Docker, `localhost:3001` → el otro). Para ese proceso o cambia el puerto en `.env`. |
| Los cambios del frontend no se ven | Comprueba que no has puesto `NEXT_DEV_BUNDLER=turbopack` en Windows; si sigue, `docker compose restart interfaces`. |
| Errores de módulos tras cambiar dependencias JS | `docker compose up --build --renew-anon-volumes`. |
| El backoffice dice «No se pudo conectar con la API de TrackFlow» | La API está parada o `NEXT_PUBLIC_API_BASE_URL` no es una URL que resuelva el navegador (`localhost`, no `backend`). En producción: abre el túnel SSH. |
| Error de CORS en la consola del navegador | `CORS_ALLOWED_ORIGINS` no incluye el origen exacto del backoffice (puerto incluido). |
| `required variable IMAGE_TAG is missing a value` | Falta `IMAGE_TAG` en el `.env` del VPS o en `$env:IMAGE_TAG` al compilar. |
| Producción: `No such image: trackflow-backend:<etiqueta>` | La imagen de esa etiqueta no está cargada en el VPS (`pull_policy: never`): repite el `docker save … \| docker load`. |
| `docker load` falla o la imagen llega corrupta al usar una tubería de PowerShell | Usa la variante `cmd /c "…"`: las tuberías de PowerShell 5.1 no son binarias. |
