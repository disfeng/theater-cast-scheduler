#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_ROOT=$(mktemp -d)
TEST_PIDS=''

cleanup() {
  local pid

  for pid in $TEST_PIDS; do
    kill "$pid" 2>/dev/null || true
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

assert_process_stopped() {
  local pid=$1
  local message=$2

  if kill -0 "$pid" 2>/dev/null; then
    fail "$message (PID $pid is still running)"
  fi
}

wait_for_file() {
  local file=$1
  local attempts=0

  while [ ! -s "$file" ] && [ "$attempts" -lt 100 ]; do
    sleep 0.05
    attempts=$((attempts + 1))
  done
  [ -s "$file" ] || fail "timed out waiting for $file"
}

make_fake_project() {
  local name=$1

  FAKE_PROJECT="$TMP_ROOT/$name"
  mkdir -p \
    "$FAKE_PROJECT/backend/.venv/bin" \
    "$FAKE_PROJECT/frontend/node_modules" \
    "$FAKE_PROJECT/bin"
  cp "$PROJECT_ROOT/dev.sh" "$FAKE_PROJECT/dev.sh"
  chmod +x "$FAKE_PROJECT/dev.sh"

  FAKE_EVENTS="$FAKE_PROJECT/events"
  FAKE_BACKEND_PID="$FAKE_PROJECT/backend-pid"
  FAKE_FRONTEND_PID="$FAKE_PROJECT/frontend-pid"
  : > "$FAKE_EVENTS"

  apply_fake_executables
}

apply_fake_executables() {
  local alembic="$FAKE_PROJECT/backend/.venv/bin/alembic"
  local uvicorn="$FAKE_PROJECT/backend/.venv/bin/uvicorn"
  local npm="$FAKE_PROJECT/bin/npm"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [ "${FAKE_MIGRATION_FAIL:-0}" = "1" ]; then' \
    '  exit 23' \
    'fi' \
    "printf 'migrated\\n' >> \"\$FAKE_EVENTS\"" \
    > "$alembic"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    "printf '%s\\n' \"\$\$\" > \"\$FAKE_BACKEND_PID\"" \
    "printf 'backend-started\\n' >> \"\$FAKE_EVENTS\"" \
    'if [ "${FAKE_BACKEND_EXIT:-0}" = "1" ]; then' \
    '  exit 7' \
    'fi' \
    "trap 'exit 0' TERM INT" \
    'while :; do sleep 1; done' \
    > "$uvicorn"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    "printf '%s\\n' \"\$\$\" > \"\$FAKE_FRONTEND_PID\"" \
    "printf 'frontend-started\\n' >> \"\$FAKE_EVENTS\"" \
    "trap 'exit 0' TERM INT" \
    'while :; do sleep 1; done' \
    > "$npm"

  chmod +x "$alembic" "$uvicorn" "$npm"
}

run_dev() {
  set +e
  RUN_OUTPUT=$(
    cd "$FAKE_PROJECT" &&
      PATH="$FAKE_PROJECT/bin:$PATH" \
      FAKE_EVENTS="$FAKE_EVENTS" \
      FAKE_BACKEND_PID="$FAKE_BACKEND_PID" \
      FAKE_FRONTEND_PID="$FAKE_FRONTEND_PID" \
      FAKE_MIGRATION_FAIL="${FAKE_MIGRATION_FAIL:-0}" \
      FAKE_BACKEND_EXIT="${FAKE_BACKEND_EXIT:-0}" \
      ./dev.sh 2>&1
  )
  RUN_STATUS=$?
  set -e
}

test_missing_backend_environment() {
  make_fake_project missing-backend
  rm -rf "$FAKE_PROJECT/backend/.venv"

  run_dev

  assert_nonzero "$RUN_STATUS" "missing backend environment must fail"
  assert_contains "$RUN_OUTPUT" "backend" "failure must identify the backend setup"
  assert_contains "$RUN_OUTPUT" "install" "failure must mention the backend installation step"
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

test_term_cleans_up_both_services() {
  local dev_pid
  local backend_pid
  local frontend_pid

  make_fake_project term-cleanup

  (
    cd "$FAKE_PROJECT" &&
      PATH="$FAKE_PROJECT/bin:$PATH" \
      FAKE_EVENTS="$FAKE_EVENTS" \
      FAKE_BACKEND_PID="$FAKE_BACKEND_PID" \
      FAKE_FRONTEND_PID="$FAKE_FRONTEND_PID" \
      ./dev.sh
  ) &
  dev_pid=$!
  TEST_PIDS="$TEST_PIDS $dev_pid"

  wait_for_file "$FAKE_BACKEND_PID"
  wait_for_file "$FAKE_FRONTEND_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  TEST_PIDS="$TEST_PIDS $backend_pid $frontend_pid"

  kill -TERM "$dev_pid"
  wait "$dev_pid" 2>/dev/null || true

  assert_process_stopped "$backend_pid" "TERM must stop the backend"
  assert_process_stopped "$frontend_pid" "TERM must stop the frontend"
}

test_missing_backend_environment
test_migration_failure
test_backend_exit_cleans_up_frontend
test_term_cleans_up_both_services

printf 'dev.sh tests passed\n'
