#!/usr/bin/env bash
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_PID=''
FRONTEND_PID=''

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

stop_service() {
  service_pid=$1
  attempts=0

  [ -n "$service_pid" ] || return 0

  if kill -0 "$service_pid" 2>/dev/null; then
    kill -TERM "$service_pid" 2>/dev/null || true
    while kill -0 "$service_pid" 2>/dev/null && [ "$attempts" -lt 50 ]; do
      sleep 0.1
      attempts=$((attempts + 1))
    done
    if kill -0 "$service_pid" 2>/dev/null; then
      kill -KILL "$service_pid" 2>/dev/null || true
    fi
  fi

  wait "$service_pid" 2>/dev/null || true
}

cleanup() {
  status=$?
  trap - EXIT INT TERM
  stop_service "$BACKEND_PID"
  stop_service "$FRONTEND_PID"
  exit "$status"
}

handle_signal() {
  exit "$1"
}

trap cleanup EXIT
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

[ -x "$ROOT_DIR/backend/.venv/bin/alembic" ] ||
  fail 'backend environment is missing; install backend dependencies first'
[ -x "$ROOT_DIR/backend/.venv/bin/uvicorn" ] ||
  fail 'backend uvicorn is missing; install backend dependencies first'
[ -d "$ROOT_DIR/frontend/node_modules" ] ||
  fail 'frontend dependencies are missing; run npm install in frontend first'
command -v npm >/dev/null 2>&1 ||
  fail 'npm is not available; install npm and frontend dependencies first'

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  . "$ROOT_DIR/.env"
  set +a
fi

(
  cd "$ROOT_DIR/backend"
  exec .venv/bin/alembic upgrade head
)

(
  cd "$ROOT_DIR/backend"
  exec .venv/bin/uvicorn app.main:app --reload
) &
BACKEND_PID=$!

(
  cd "$ROOT_DIR/frontend"
  exec npm run dev
) &
FRONTEND_PID=$!

while :; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    set +e
    wait "$BACKEND_PID"
    service_status=$?
    set -e
    BACKEND_PID=''
    stop_service "$FRONTEND_PID"
    FRONTEND_PID=''
    exit "$service_status"
  fi

  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    set +e
    wait "$FRONTEND_PID"
    service_status=$?
    set -e
    FRONTEND_PID=''
    stop_service "$BACKEND_PID"
    BACKEND_PID=''
    exit "$service_status"
  fi

  sleep 1
done
