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

stop_recorded_services() {
  local pid_file
  local pid

  for pid_file in \
    "$TMP_ROOT"/*/backend-pid \
    "$TMP_ROOT"/*/frontend-pid \
    "$TMP_ROOT"/*/backend-child-pid \
    "$TMP_ROOT"/*/frontend-child-pid; do
    [ -s "$pid_file" ] || continue
    pid=$(<"$pid_file")
    case "$pid" in
      *[!0-9]*|'') continue ;;
    esac
    force_stop "$pid"
  done
}

cleanup() {
  local pid

  for pid in $TEST_PIDS; do
    force_stop "$pid"
  done
  stop_recorded_services
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
    stop_recorded_services
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

assert_database_not_created() {
  local database

  database=$(find "$FAKE_PROJECT" -name fake-startup-test.db -print -quit)
  [ -z "$database" ] || fail "startup must not create the database ($database)"
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
  FAKE_BACKEND_CHILD_PID="$FAKE_PROJECT/backend-child-pid"
  FAKE_FRONTEND_CHILD_PID="$FAKE_PROJECT/frontend-child-pid"
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
    'if [ "${FAKE_SIGNAL_DURING_BACKEND_START:-0}" = "1" ]; then' \
    '  kill -TERM "$PPID"' \
    'fi' \
    "trap 'if [ \"\${FAKE_SLOW_TERM:-0}\" = \"1\" ]; then sleep 0.3; fi; exit 0' TERM INT" \
    'if [ "${FAKE_SPAWN_DESCENDANTS:-0}" = "1" ]; then' \
    "  ( trap 'exit 0' TERM INT; while :; do sleep 1; done ) &" \
    "  printf '%s\\n' \"\$!\" > \"\$FAKE_BACKEND_CHILD_PID\"" \
    'fi' \
    'while :; do sleep 1; done' \
    > "$uvicorn"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [ "${1:-}" = "install" ] || [ "${1:-}" = "ci" ]; then' \
    "  printf 'frontend-installed\\n' >> \"\$FAKE_EVENTS\"" \
    "  printf 'startup must not install frontend dependencies\\n' >&2" \
    '  exit 26' \
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
    "trap 'if [ \"\${FAKE_SLOW_TERM:-0}\" = \"1\" ]; then sleep 0.3; fi; exit 0' TERM INT" \
    'if [ "${FAKE_SPAWN_DESCENDANTS:-0}" = "1" ]; then' \
    "  ( trap 'exit 0' TERM INT; while :; do sleep 1; done ) &" \
    "  printf '%s\\n' \"\$!\" > \"\$FAKE_FRONTEND_CHILD_PID\"" \
    'fi' \
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
  set -m
  (
    trap - INT
    cd "$FAKE_PROJECT"
    exec env \
      PATH="$FAKE_PROJECT/bin:$PATH" \
      FAKE_EVENTS="$FAKE_EVENTS" \
      FAKE_BACKEND_PID="$FAKE_BACKEND_PID" \
      FAKE_FRONTEND_PID="$FAKE_FRONTEND_PID" \
      FAKE_BACKEND_CHILD_PID="$FAKE_BACKEND_CHILD_PID" \
      FAKE_FRONTEND_CHILD_PID="$FAKE_FRONTEND_CHILD_PID" \
      FAKE_MIGRATION_FAIL="${FAKE_MIGRATION_FAIL:-0}" \
      FAKE_BACKEND_EXIT="${FAKE_BACKEND_EXIT:-0}" \
      FAKE_FRONTEND_EXIT="${FAKE_FRONTEND_EXIT:-0}" \
      FAKE_SPAWN_DESCENDANTS="${FAKE_SPAWN_DESCENDANTS:-0}" \
      FAKE_SIGNAL_DURING_BACKEND_START="${FAKE_SIGNAL_DURING_BACKEND_START:-0}" \
      FAKE_SLOW_TERM="${FAKE_SLOW_TERM:-0}" \
      ./dev.sh
  ) > "$RUN_OUTPUT_FILE" 2>&1 &
  DEV_PID=$!
  set +m
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
  assert_database_not_created
}

test_missing_frontend_dependencies() {
  make_fake_project missing-frontend
  rm -rf "$FAKE_PROJECT/frontend/node_modules"

  run_dev

  assert_nonzero "$RUN_STATUS" "missing frontend dependencies must fail"
  assert_contains "$RUN_OUTPUT" "npm" "failure must identify the frontend package manager"
  assert_contains "$RUN_OUTPUT" "install" "failure must mention npm install"
  [ ! -e "$FAKE_PROJECT/frontend/node_modules" ] || fail "missing frontend dependencies must not be installed"
  assert_file_not_contains "$FAKE_EVENTS" "backend-installed" "backend dependencies must not be installed"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-installed" "frontend dependencies must not be installed"
  assert_file_not_contains "$FAKE_EVENTS" "backend-started" "backend must not start"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-started" "frontend must not start"
  assert_database_not_created
}

test_migration_failure() {
  make_fake_project migration-failure

  FAKE_MIGRATION_FAIL=1 run_dev

  assert_status 23 "$RUN_STATUS" "migration failure status must propagate"
  assert_file_not_contains "$FAKE_EVENTS" "backend-started" "backend must not start after migration failure"
  assert_file_not_contains "$FAKE_EVENTS" "frontend-started" "frontend must not start after migration failure"
  assert_database_not_created
}

test_backend_exit_cleans_up_frontend() {
  local frontend_pid
  local frontend_child_pid

  make_fake_project backend-exit

  FAKE_SPAWN_DESCENDANTS=1 FAKE_BACKEND_EXIT=1 run_dev

  assert_status 7 "$RUN_STATUS" "backend exit status must propagate"
  assert_file_contains "$FAKE_EVENTS" "backend-started" "backend must start"
  assert_file_contains "$FAKE_EVENTS" "frontend-started" "frontend must start"
  wait_for_file "$FAKE_FRONTEND_PID"
  wait_for_file "$FAKE_FRONTEND_CHILD_PID"
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  frontend_child_pid=$(<"$FAKE_FRONTEND_CHILD_PID")
  assert_process_stopped "$frontend_pid" "frontend sibling must be terminated"
  assert_process_stopped "$frontend_child_pid" "frontend sibling descendant must be terminated"
  assert_database_not_created
}

test_frontend_exit_cleans_up_backend() {
  local backend_pid
  local backend_child_pid

  make_fake_project frontend-exit

  FAKE_SPAWN_DESCENDANTS=1 FAKE_FRONTEND_EXIT=1 run_dev

  assert_status 9 "$RUN_STATUS" "frontend exit status must propagate"
  assert_file_contains "$FAKE_EVENTS" "backend-started" "backend must start"
  assert_file_contains "$FAKE_EVENTS" "frontend-started" "frontend must start"
  wait_for_file "$FAKE_BACKEND_PID"
  wait_for_file "$FAKE_BACKEND_CHILD_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  backend_child_pid=$(<"$FAKE_BACKEND_CHILD_PID")
  assert_process_stopped "$backend_pid" "backend sibling must be terminated"
  assert_process_stopped "$backend_child_pid" "backend sibling descendant must be terminated"
  assert_database_not_created
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
  assert_database_not_created
}

test_signal_cleans_up_both_services() {
  local signal=$1
  local backend_pid
  local frontend_pid
  local backend_child_pid
  local frontend_child_pid

  make_fake_project "${signal}-cleanup"
  FAKE_SPAWN_DESCENDANTS=1 start_dev

  wait_for_file "$FAKE_BACKEND_PID"
  wait_for_file "$FAKE_FRONTEND_PID"
  wait_for_file "$FAKE_BACKEND_CHILD_PID"
  wait_for_file "$FAKE_FRONTEND_CHILD_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  backend_child_pid=$(<"$FAKE_BACKEND_CHILD_PID")
  frontend_child_pid=$(<"$FAKE_FRONTEND_CHILD_PID")
  TEST_PIDS="$TEST_PIDS $backend_pid $frontend_pid $backend_child_pid $frontend_child_pid"

  kill -"$signal" "$DEV_PID"
  wait_for_process_exit "$DEV_PID" "dev.sh after $signal"

  assert_process_stopped "$backend_pid" "$signal must stop the backend"
  assert_process_stopped "$frontend_pid" "$signal must stop the frontend"
  assert_process_stopped "$backend_child_pid" "$signal must stop the backend descendant"
  assert_process_stopped "$frontend_child_pid" "$signal must stop the frontend descendant"
  assert_database_not_created
}

test_signal_during_backend_launch_cleans_up() {
  local backend_pid

  make_fake_project signal-during-launch
  FAKE_SIGNAL_DURING_BACKEND_START=1 start_dev

  wait_for_file "$FAKE_BACKEND_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  TEST_PIDS="$TEST_PIDS $backend_pid"
  wait_for_process_exit "$DEV_PID" "dev.sh after signal during backend launch"

  assert_status 143 "$WAIT_STATUS" "deferred startup signal status must propagate"
  assert_process_stopped "$backend_pid" "startup signal must stop the recorded backend"
  assert_database_not_created
}

test_repeated_signals_finish_cleanup() {
  local backend_pid
  local frontend_pid

  make_fake_project repeated-signals
  FAKE_SLOW_TERM=1 start_dev

  wait_for_file "$FAKE_BACKEND_PID"
  wait_for_file "$FAKE_FRONTEND_PID"
  backend_pid=$(<"$FAKE_BACKEND_PID")
  frontend_pid=$(<"$FAKE_FRONTEND_PID")
  TEST_PIDS="$TEST_PIDS $backend_pid $frontend_pid"

  kill -TERM "$DEV_PID"
  sleep "$WAIT_INTERVAL"
  kill -TERM "$DEV_PID" 2>/dev/null || true
  wait_for_process_exit "$DEV_PID" "dev.sh after repeated signals"

  assert_process_stopped "$backend_pid" "repeated signals must not interrupt backend cleanup"
  assert_process_stopped "$frontend_pid" "repeated signals must not interrupt frontend cleanup"
  assert_database_not_created
}

test_missing_backend_environment
test_missing_frontend_dependencies
test_migration_failure
test_backend_exit_cleans_up_frontend
test_frontend_exit_cleans_up_backend
test_normal_exit_cleans_up_sibling
test_signal_during_backend_launch_cleans_up
test_repeated_signals_finish_cleanup
test_signal_cleans_up_both_services INT
test_signal_cleans_up_both_services TERM

printf 'dev.sh tests passed\n'
