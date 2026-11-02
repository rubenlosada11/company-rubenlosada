# syntax=docker/dockerfile:1
# Contenedor "interfaces": website (:3000) y backoffice (:3001), dos apps Next.js independientes.
# Contexto de build: uis/ (ver uis/.dockerignore).
#
#   --target dev   next dev; el código llega por bind mount (docker-compose.yml)
#   --target prod  next build + next start; imagen autocontenida (docker-compose.prod.yml)
#
# Cada app instala sus dependencias con su propio package-lock.json (`npm ci`): no se comparten node_modules.

ARG NODE_IMAGE=node:24.19.0-alpine3.24

# ---------------------------------------------------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS base
# tini como PID 1: reenvía señales a start.sh y recoge procesos zombis.
RUN apk add --no-cache tini
ENV NEXT_TELEMETRY_DISABLED=1
COPY start.sh /usr/local/bin/start.sh
# core.autocrlf de Windows puede dejar el script con CRLF: se normaliza a LF.
RUN sed -i 's/\r$//' /usr/local/bin/start.sh && chmod 0755 /usr/local/bin/start.sh
# WORKDIR crearía las carpetas como root; npm ci y next corren como el usuario sin privilegios `node`.
RUN mkdir -p /app/website /app/backoffice && chown -R node:node /app
WORKDIR /app
EXPOSE 3000 3001
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/start.sh"]

# --- Dependencias completas (incluye devDependencies: next build y next dev las necesitan) ---------------------------
FROM base AS deps-website
WORKDIR /app/website
COPY --chown=node:node website/package.json website/package-lock.json ./
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci --no-audit --no-fund

FROM base AS deps-backoffice
WORKDIR /app/backoffice
COPY --chown=node:node backoffice/package.json backoffice/package-lock.json ./
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci --no-audit --no-fund

# --- Desarrollo ------------------------------------------------------------------------------------------------------
# Solo node_modules: el código se monta encima. Docker Compose protege node_modules y .next con volúmenes anónimos,
# que se inicializan con el contenido (y el propietario) de estas carpetas.
FROM base AS dev
ENV NODE_ENV=development
COPY --from=deps-website /app/website/node_modules /app/website/node_modules
COPY --from=deps-backoffice /app/backoffice/node_modules /app/backoffice/node_modules
RUN mkdir -p /app/website/.next /app/backoffice/.next && chown node:node /app/website/.next /app/backoffice/.next
USER node
CMD ["dev"]

# --- Build de producción ---------------------------------------------------------------------------------------------
FROM deps-website AS build-website
COPY --chown=node:node website/ ./
RUN npm run build && rm -rf .next/cache

FROM deps-backoffice AS build-backoffice
# Next.js incrusta las NEXT_PUBLIC_* en el bundle durante `next build`: son públicas, nunca secretos.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_INVENTORY_API_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_INVENTORY_API_URL=${NEXT_PUBLIC_INVENTORY_API_URL}
COPY --chown=node:node backoffice/ ./
RUN test -n "$NEXT_PUBLIC_API_BASE_URL" || { echo "Falta el build-arg NEXT_PUBLIC_API_BASE_URL" >&2; exit 1; }
RUN npm run build && rm -rf .next/cache

# --- Dependencias de ejecución (sin devDependencies) -----------------------------------------------------------------
FROM base AS runtime-deps-website
WORKDIR /app/website
COPY --chown=node:node website/package.json website/package-lock.json ./
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci --omit=dev --no-audit --no-fund

FROM base AS runtime-deps-backoffice
WORKDIR /app/backoffice
COPY --chown=node:node backoffice/package.json backoffice/package-lock.json ./
USER node
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 npm ci --omit=dev --no-audit --no-fund

# --- Producción ------------------------------------------------------------------------------------------------------
FROM base AS prod
ENV NODE_ENV=production
COPY --from=runtime-deps-website /app/website/node_modules /app/website/node_modules
COPY --from=build-website /app/website/package.json /app/website/next.config.ts /app/website/
COPY --from=build-website /app/website/public /app/website/public
COPY --from=build-website /app/website/.next /app/website/.next
COPY --from=runtime-deps-backoffice /app/backoffice/node_modules /app/backoffice/node_modules
COPY --from=build-backoffice /app/backoffice/package.json /app/backoffice/next.config.ts /app/backoffice/
COPY --from=build-backoffice /app/backoffice/public /app/backoffice/public
COPY --from=build-backoffice /app/backoffice/.next /app/backoffice/.next
USER node
CMD ["prod"]
