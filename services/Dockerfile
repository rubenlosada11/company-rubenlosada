# syntax=docker/dockerfile:1
# Contenedor "backend": API FastAPI de services/api (entrypoint app.main:app, ver pyproject.toml), puerto 8000.
#
# Contexto de build: services/ (ver services/.dockerignore), más el contexto adicional "packages" con el paquete local
# packages/analisis-incidencias, que la API usa como dependencia:
#   docker build --build-context packages=packages/analisis-incidencias -f services/Dockerfile services
# (Docker Compose lo pasa con `additional_contexts`).
#
#   --target dev   uvicorn --reload; el código llega por bind mount (docker-compose.yml)
#   --target prod  uvicorn sin --reload, un solo worker; código incluido en la imagen (docker-compose.prod.yml)
#
# Dependencias: services/requirements.txt, generado desde services/api/uv.lock (fuente de verdad) con hashes. Para
# regenerarlo tras cambiar dependencias, desde services/api:
#   uv export --frozen --format requirements.txt --no-dev --no-emit-project --no-emit-package analisis-incidencias --output-file ../requirements.txt
#
# La API NO se instala como paquete: busca sus bases en <código>/db (Path(__file__)), así que se ejecuta desde el código
# fuente con PYTHONPATH. Los datos viven en /app/services/api/db (bind mount en dev, volumen en prod).

ARG PYTHON_IMAGE=python:3.13.18-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.19

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/services/api:/app/packages/analisis-incidencias/src \
    UV_LINK_MODE=copy
COPY --from=uv /uv /usr/local/bin/uv

# Usuario sin privilegios (uid/gid 1000).
RUN groupadd --gid 1000 trackflow \
 && useradd --uid 1000 --gid trackflow --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin trackflow

# Dependencias de terceros, con versiones y hashes del lock (--require-hashes falla si algo no coincide).
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --require-hashes --no-deps -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Paquete local (solo biblioteca estándar): basta con su código en PYTHONPATH.
COPY --from=packages src /app/packages/analisis-incidencias/src

WORKDIR /app/services/api
# La carpeta de datos es lo único en lo que escribe la API.
RUN mkdir -p db && chown trackflow:trackflow db
EXPOSE 8000

# --- Desarrollo ------------------------------------------------------------------------------------------------------
# services/api y packages/analisis-incidencias llegan por bind mount. Solo se vigila el código (no .venv, db/ ni tests).
FROM base AS dev
USER trackflow
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "app", "--reload-dir", "/app/packages/analisis-incidencias/src"]

# --- Producción ------------------------------------------------------------------------------------------------------
# Un solo worker: la API guarda el último análisis en memoria y protege TinyDB/SQLite con candados de hilo.
FROM base AS prod
COPY api/app ./app
USER trackflow
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
