#!/bin/sh
# Arranca website (:3000) y backoffice (:3001) en el mismo contenedor y los vigila.
#
#   start.sh dev    next dev   (código montado por bind mount, recarga en caliente)
#   start.sh prod   next start (build de producción incluido en la imagen)
#
# - SIGTERM / SIGINT se reenvían a las dos apps y se espera a que terminen (sin procesos huérfanos).
# - Si una app termina sola, se para la otra y el contenedor sale con error para que Docker lo reinicie.
# - Cada línea de log lleva el prefijo [website] o [backoffice].
# - NEXT_DEV_BUNDLER=webpack (solo en dev) cambia Turbopack por webpack; con WATCHPACK_POLLING=true vigila los ficheros
#   por sondeo, para bind mounts que no propagan eventos (Docker Desktop en Windows).
# tini (PID 1) reenvía las señales a este script y recoge los procesos zombis.
set -eu

MODE="${1:-dev}"
case "$MODE" in
  dev) NEXT_CMD="dev" ;;
  prod) NEXT_CMD="start" ;;
  *)
    echo "start.sh: modo desconocido '$MODE' (usa dev o prod)" >&2
    exit 64
    ;;
esac

NEXT_EXTRA=""
if [ "$MODE" = "dev" ] && [ "${NEXT_DEV_BUNDLER:-}" = "webpack" ]; then
  NEXT_EXTRA="--webpack"
fi

LOG_DIR="$(mktemp -d)"

# start_app <nombre> <carpeta> <puerto>: lanza `next` en segundo plano y deja su PID en APP_PID.
start_app() {
  fifo="$LOG_DIR/$1"
  mkfifo "$fifo"
  # Lector del log con prefijo; termina solo cuando la app cierra su salida.
  (while IFS= read -r line; do printf '[%s] %s\n' "$1" "$line"; done < "$fifo") &
  # `exec` sustituye el subshell por `next`: el PID de `$!` es el del propio servidor.
  # shellcheck disable=SC2086 # NEXT_EXTRA vacío o una sola opción.
  (cd "/app/$2" && exec ./node_modules/.bin/next "$NEXT_CMD" --hostname 0.0.0.0 --port "$3" $NEXT_EXTRA) \
    > "$fifo" 2>&1 &
  APP_PID=$!
  echo "[start.sh] $1 ($NEXT_CMD) en 0.0.0.0:$3, PID $APP_PID"
}

stop_apps() {
  kill -TERM "$WEBSITE_PID" "$BACKOFFICE_PID" 2>/dev/null || true
  wait "$WEBSITE_PID" 2>/dev/null || true
  wait "$BACKOFFICE_PID" 2>/dev/null || true
  wait 2>/dev/null || true # lectores de log
  rm -rf "$LOG_DIR"
}

# shellcheck disable=SC2329 # se invoca desde `trap`.
on_signal() {
  trap - TERM INT
  echo "[start.sh] señal $1 recibida: parando las dos apps"
  stop_apps
  echo "[start.sh] apps paradas"
  exit "$2"
}

start_app website website 3000
WEBSITE_PID=$APP_PID
start_app backoffice backoffice 3001
BACKOFFICE_PID=$APP_PID

trap 'on_signal TERM 143' TERM
trap 'on_signal INT 130' INT

# `sleep & wait` en lugar de `sleep` a secas: `wait` se interrumpe con la señal y el trap actúa al momento.
while kill -0 "$WEBSITE_PID" 2>/dev/null && kill -0 "$BACKOFFICE_PID" 2>/dev/null; do
  sleep 1 &
  wait $! || true
done

trap - TERM INT
if kill -0 "$WEBSITE_PID" 2>/dev/null; then FAILED=backoffice; FAILED_PID=$BACKOFFICE_PID; else FAILED=website; FAILED_PID=$WEBSITE_PID; fi
STATUS=0
wait "$FAILED_PID" || STATUS=$?
echo "[start.sh] $FAILED ha terminado (código $STATUS): parando la otra app" >&2
stop_apps
# Una app que termina sola es siempre un fallo para el contenedor, aunque saliera con 0.
[ "$STATUS" -eq 0 ] && STATUS=1
exit "$STATUS"
