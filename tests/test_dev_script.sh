#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_ROOT=$(mktemp -d)
TEST_PIDS=''
WAIT_ATTEMPTS=200
WAIT_INTERVAL=0.05

process_is_running() {
  kill -0 "$1" 2>/dev/null
}

force_stop() {
  local pid=$1
  local attempts=0

  process_is_running "$pid" || return 0
  kill -TERM "$pid" 2>/dev/null || true
  while process_is_running "$pid" && [ "$attempts" -lt 20 ]; do
    sleep "$WAIT_INTERVAL"
    attempts=$((attempts + 1))
  done
  if process_is_running "$pid"; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  local pid

  for pid in $TEST_PIDS; do
    force_stop "$pid"
  done
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_status() {
  local expected=$1
  local actual=$2
  local message=$3

  [ "$actual" -eq "$expected" ] ||
    fail "$message (expected status $expected, got $actual)"
}

assert_nonzero() {
  local actual=$1
  local message=$2

  [ "$actual" -ne 0 ] || fail "$message (expected a nonzero status)"
}

assert_contains() {
  local haystack=$1
  local needle=$2
  local message=$3

  case "$haystack" in
    *"$needle"*) ;;
    *) fail "$message (missing: $needle)" ;;
  esac
}

assert_file_contains() {
  local file=$1
  local needle=$2
  local message=$3

  [ -f "$file" ] || fail "$message (missing file: $file)"
  grep -Fqx "$needle" "$file" || fail "$message (missing event: $needle)"
}

assert_file_not_contains() {
  local file=$1
  local needle=$2
  local message=$3

  if [ -f "$file" ] && grep -Fqx "$needle" "$file"; then
    fail "$message (unexpected event: $needle)"
  fi
}

wait_for_file() {
  local file=$1
  local attempts=0

  while [ ! -s "$file" ] && [ "$attempts" -lt "$WAIT_ATTEMPTS" ]; do
    sleep "$WAIT_INTERVAL"
    attempts=$((attempts + 1))
  done
  [ -s "$file" ] || fail "timed out waiting for $file"
}

wait_for_process_exit() {
  local pid=$1
  local description=$2
  local attempts=0

  while process_is_running "$pid" && [ "$attempts" -lt "$WAIT_ATTEMPTS" ]; do
    sleep "$WAIT_INTERVAL"
    attempts=$((attempts + 1))
  done
  if process_is_running "$pid"; then
    force_stop "$pid"
    fail "timed out waiting for $description (PID $pid)"
  fi

  set +e
  wait "$pid"
  WAIT_STATUS=$?
  set -e
}

assert_process_stopped() {
  local pid=$1
  local message=$2
  local attempts=0

  while process_is_running "$pid" && [ "$attempts" -lt "$WAIT_ATTEMPTS" ]; do
    sleep "$WAIT_INTERVAL"
    attempts=$((attempts + 1))
  done
  if process_is_running "$pid"; then
    force_stop "$pid"
    fail "$message (PID $pid is still running)"
  fi
}

make_fake_project() {
  local name=$1

  FAKE_PROJECT="$TMP_ROOT/假 项目 $name"
  mkdir -p \
    "$FAKE_PROJECT/backend/.venv/bin" \
    "$FAKE_PROJECT/frontend/node_modules" \
    "$FAKE_PROJECT/bin"
  cp "$PROJECT_ROOT/dev.sh" "$FAKE_PROJECT/dev.sh"
  chmod +x "$FAKE_PROJECT/dev.sh"

  FAKE_EVENTS="$FAKE_PROJECT/events"
  FAKE_BACKEND_PID="$FAKE_PROJECT/backend-pid"
  FAKE_FRONTEND_PID="$FAKE_PROJECT/frontend-pid"
  RUN_OUTPUT_FILE="$FAKE_PROJECT/dev-output"
  : > "$FAKE_EVENTS"
  printf '%s\n' \
    'DATABASE_URL=sqlite:///fake-startup-test.db' \
    'JWT_SECRET=fake-startup-secret' \
    > "$FAKE_PROJECT/.env"

  apply_fake_executables
}

apply_fake_executables() {
  local alembic="$FAKE_PROJECT/backend/.venv/bin/alembic"
  local uvicorn="$FAKE_PROJECT/backend/.venv/bin/uvicorn"
  local npm="$FAKE_PROJECT/bin/npm"
  local python3="$FAKE_PROJECT/bin/python3"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [ "${DATABASE_URL:-}" != "sqlite:///fake-startup-test.db" ] || [ "${JWT_SECRET:-}" != "fake-startup-secret" ]; then' \
    "  printf 'environment-not-loaded\\n' >&2" \
    '  exit 25' \
    'fi' \
    'if [ "$#" -ne 2 ] || [ "$1" != "upgrade" ] || [ "$2" != "head" ]; then' \
    "  printf 'expected alembic upgrade head\\n' >&2" \
    '  exit 24' \
    'fi' \
    'if [ "${FAKE_MIGRATION_FAIL:-0}" = "1" ]; then' \
    '  exit 23' \
    'fi' \
    "printf 'migrated\\n' >> \"\$FAKE_EVENTS\"" \
    > "$alembic"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [ "${DATABASE_URL:-}" != "sqlite:///fake-startup-test.db" ] || [ "${JWT_SECRET:-}" != "fake-startup-secret" ]; then' \
    "  printf 'environment-not-loaded\\n' >&2" \
    '  exit 25' \
    'fi' \
    "printf '%s\\n' \"\$\$\" > \"\$FAKE_BACKEND_PID\"" \
    "printf 'backend-started\\n' >> \"\$FAKE_EVENTS\"" \
    'if [ "${FAKE_BACKEND_EXIT:-0}" = "1" ]; then' \
    '  exit 7' \
    'fi' \
    'if [ "${FAKE_BACKEND_EXIT:-0}" = "normal" ]; then' \
    '  exit 0' \
    'fi' \
    "trap 'exit 0' TERM INT" \
    'while :; do sleep 1; done' \
    > "$uvicorn"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [ "${1:-}" = "install" ] || [ "${1:-}" = "ci" ]; then' \
    "  printf 'frontend-installed\\n' >> \"\$FAKE_EVENTS\"" \
    '  exit 0' \
    'fi' \
    'if [ "${DATABASE_URL:-}" != "sqlite:///fake-startup-test.db" ] || [ "${JWT_SECRET:-}" != "fake-startup-secret" ]; then' \
    "  printf 'environment-not-loaded\\n' >&2" \
    '  exit 25' \
    'fi' \
    "printf '%s\\n' \"\$\$\" > \"\$FAKE_FRONTEND_PID\"" \
    "printf 'frontend-started\\n' >> \"\$FAKE_EVENTS\"" \
    'if [ "${FAKE_FRONTEND_EXIT:-0}" = "1" ]; then' \
    '  exit 9' \
    'fi' \
    "trap 'exit 0' TERM INT" \
    'while :; do sleep 1; done' \
    > "$npm"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    "printf 'backend-installed\\n' >> \"\$FAKE_EVENTS\"" \
    > "$python3"

  chmod +x "$alembic" "$uvicorn" "$npm" "$python3"
}

start_dev() {
  : > "$RUN_OUTPUT_FILE"
  (
    cd "$FAKE_PROJECT" &&
      env \
        PATH="$FAKE_PROJECT/bin:$PATH" \
        FAKE_EVENTS="$FAKE_EVENTS" \
        FAKE_BACKEND_PID="$FAKE_BACKEND_PID" \
        FAKE_FRONTEND_PID="$FAKE_FRONTEND_PID" \
        FAKE_MIGRATION_FAIL="${FAKE_MIGRATION_FAIL:-0}" \
        FAKE_BACKEND_EXIT="${FAKE_BACKEND_EXIT:-0}" \
        FAKE_FRONTEND_EXIT="${FAKE_FRONTEND_EXIT:-0}" \
        ./dev.sh
  ) > "$RUN_OUTPUT_FILE" 2>&1 &
  DEV_PID=$!
  TEST_PIDS="$TEST_PIDS $DEV_PID"
}

run_dev() {
  start_dev
  wait_for_process_exit "$DEV_PID" "dev.sh"
  RUN_STATUS=$WAIT_STATUS
  RUN_OUTPUT=$(<"$RUN_OUTPUT_FILE")
}

test_missing_backend_environment() {
  make_fake_project missing-backend
  rm -rf "$FAKE_PROJECT/backend/.venv"

  run_dev

  assert_nonzero "$RUN_STATUS" "missing backend environment must fail"
  assert_contains "$RUN_OUTPUT" "backend" "failure must identify the backend setup"
  assert_contains "$RUN_OUTPUT" "install" "failure must mention the backend installation step"
  [ ! -e "$FAKE_PROJECT/backend/.venv" ] || fail "missing backend environment must not be created"
  assert_file_not_contains "$FAKE_EVENTS" "backend-installed" "backend dependencies must not be installed"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-installed" "frontend dependencies must not be installed"
  assert_file_not_contains "$FAKE_EVENTS" "backend-started" "backend must not start"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-started" "frontend must not start"
}

test_migration_failure() {
  make_fake_project migration-failure

  FAKE_MIGRATION_FAIL=1 run_dev

  assert_status 23 "$RUN_STATUS" "migration failure status must propagate"
  assert_file_not_contains "$FAKE_EVENTS" "backend-started" "backend must not start after migration failure"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-started" "frontend must not start after migration failure"
}

test_backend_exit_cleans_up_frontend() {
  local frontend_pid

  make_fake_project backend-exit

  FAKE_BACKEND_EXIT=1 run_dev

  assert_status 7 "$RUN_STATUS" "backend exit status must propagate"
  assert_file_contains "$FAKE_EVENTS" "backend-started" "backend must start"
  assert_file_contains "$FAKE_EVENTS" "frontend-started" "frontend must start"
  wait_for_file "$FAKE_FRONTEND_PID"
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  assert_process_stopped "$frontend_pid" "frontend sibling must be terminated"
}

test_frontend_exit_cleans_up_backend() {
  local backend_pid

  make_fake_project frontend-exit

  FAKE_FRONTEND_EXIT=1 run_dev

  assert_status 9 "$RUN_STATUS" "frontend exit status must propagate"
  assert_file_contains "$FAKE_EVENTS" "backend-started" "backend must start"
  assert_file_contains "$FAKE_EVENTS" "frontend-started" "frontend must start"
  wait_for_file "$FAKE_BACKEND_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  assert_process_stopped "$backend_pid" "backend sibling must be terminated"
}

test_normal_exit_cleans_up_sibling() {
  local frontend_pid

  make_fake_project normal-exit

  FAKE_BACKEND_EXIT=normal run_dev

  assert_status 0 "$RUN_STATUS" "normal service exit must propagate"
  assert_file_contains "$FAKE_EVENTS" "backend-started" "backend must start"
  assert_file_contains "$FAKE_EVENTS" "frontend-started" "frontend must start"
  wait_for_file "$FAKE_FRONTEND_PID"
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  assert_process_stopped "$frontend_pid" "normal exit must terminate the sibling"
}

test_signal_cleans_up_both_services() {
  local signal=$1
  local backend_pid
  local frontend_pid

  make_fake_project "${signal}-cleanup"
  start_dev

  wait_for_file "$FAKE_BACKEND_PID"
  wait_for_file "$FAKE_FRONTEND_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  TEST_PIDS="$TEST_PIDS $backend_pid $frontend_pid"

  kill -"$signal" "$DEV_PID"
  wait_for_process_exit "$DEV_PID" "dev.sh after $signal"

  assert_process_stopped "$backend_pid" "$signal must stop the backend"
  assert_process_stopped "$frontend_pid" "$signal must stop the frontend"
}

test_missing_backend_environment
test_migration_failure
test_backend_exit_cleans_up_frontend
test_frontend_exit_cleans_up_backend
test_normal_exit_cleans_up_sibling
test_signal_cleans_up_both_services INT
test_signal_cleans_up_both_services TERM

printf 'dev.sh tests passed\n'
