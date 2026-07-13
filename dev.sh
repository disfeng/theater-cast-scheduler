#!/usr/bin/env bash
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_PID=''
FRONTEND_PID=''
PENDING_SIGNAL_STATUS=''

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

stop_service() {
  local service_pid=$1
  local attempts=0

  [ -n "$service_pid" ] || return 0

  kill -TERM -- "-$service_pid" 2>/dev/null || true
  while kill -0 -- "-$service_pid" 2>/dev/null && [ "$attempts" -lt 50 ]; do
    sleep 0.1
    attempts=$((attempts + 1))
  done
  if kill -0 -- "-$service_pid" 2>/dev/null; then
    kill -KILL -- "-$service_pid" 2>/dev/null || true
  fi

  wait "$service_pid" 2>/dev/null || true
}

cleanup() {
  local status=$?
  trap '' INT TERM
  trap - EXIT
  stop_service "$BACKEND_PID"
  stop_service "$FRONTEND_PID"
  exit "$status"
}

handle_signal() {
  local signal_status=$1

  if [ -z "$PENDING_SIGNAL_STATUS" ]; then
    PENDING_SIGNAL_STATUS=$signal_status
  fi
}

exit_if_signaled() {
  if [ -n "$PENDING_SIGNAL_STATUS" ]; then
    exit "$PENDING_SIGNAL_STATUS"
  fi
}

job_is_running() {
  local service_pid=$1
  local running_pid

  for running_pid in $(jobs -pr); do
    if [ "$running_pid" = "$service_pid" ]; then
      return 0
    fi
  done
  return 1
}

finish_after_service_exit() {
  local exited_pid=$1
  local sibling_pid=$2
  local service_status

  set +e
  wait "$exited_pid"
  service_status=$?
  set -e

  stop_service "$exited_pid"
  stop_service "$sibling_pid"
  BACKEND_PID=''
  FRONTEND_PID=''
  exit "$service_status"
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
exit_if_signaled

set -m
(
  cd "$ROOT_DIR/backend"
  exec .venv/bin/uvicorn app.main:app --port 7004 --reload
) &
BACKEND_PID=$!
if [ -n "$PENDING_SIGNAL_STATUS" ]; then
  set +m
  exit_if_signaled
fi

(
  cd "$ROOT_DIR/frontend"
  exec npm run dev
) &
FRONTEND_PID=$!
set +m
exit_if_signaled

while :; do
  exit_if_signaled

  if ! job_is_running "$BACKEND_PID"; then
    finish_after_service_exit "$BACKEND_PID" "$FRONTEND_PID"
  fi

  if ! job_is_running "$FRONTEND_PID"; then
    finish_after_service_exit "$FRONTEND_PID" "$BACKEND_PID"
  fi

  sleep 1 || true
done
