#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  case "$1" in
    *"$2"*) ;;
    *) fail "$3 (missing: $2)" ;;
  esac
}

assert_file_line() {
  grep -Fqx "$2" "$1" || fail "$3 (missing line: $2)"
}

assert_file_missing_line() {
  if [ -f "$1" ] && grep -Fqx "$2" "$1"; then
    fail "$3 (unexpected line: $2)"
  fi
}

run_invalid_mode_test() {
  local output status
  set +e
  output=$("$PROJECT_ROOT/deploy.sh" invalid 2>&1)
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "invalid deployment mode must fail"
  assert_contains "$output" "Usage:" "invalid mode should print usage"
}

make_fake_project() {
  STAGED_FRONTEND_DIR=''
  ROLLBACK_FRONTEND_DIR=''
  PREVIOUS_SOURCE_COMMIT=''
  FAKE_ROOT="$TMP_ROOT/project"
  rm -rf "$FAKE_ROOT"
  mkdir -p "$FAKE_ROOT/backend/.venv/bin" "$FAKE_ROOT/frontend/node_modules" \
    "$FAKE_ROOT/frontend/dist" "$FAKE_ROOT/scripts" "$FAKE_ROOT/var/deploy"
  cp "$PROJECT_ROOT/scripts/deploy-lib.sh" "$FAKE_ROOT/scripts/deploy-lib.sh"
  printf '[project]\nname="fake"\n' > "$FAKE_ROOT/backend/pyproject.toml"
  printf '{"lockfileVersion":3}\n' > "$FAKE_ROOT/frontend/package-lock.json"
  printf '<html>old</html>\n' > "$FAKE_ROOT/frontend/dist/index.html"
  printf 'APP_ENV=production\nMYSQL_DATABASE=fake\nMYSQL_USER=fake\nMYSQL_PASSWORD=fake\n' \
    > "$FAKE_ROOT/backend/.env"
  EVENTS="$FAKE_ROOT/events"
  : > "$EVENTS"
}

run_dependency_test() {
  make_fake_project
  # shellcheck source=../scripts/deploy-lib.sh
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  DEPLOY_TEST_EVENTS="$EVENTS"
  PIP_INSTALL_COMMAND='printf "pip-install\\n" >> "$DEPLOY_TEST_EVENTS"'
  NPM_CI_COMMAND='printf "npm-ci:%s\\n" "$NPM_REGISTRY" >> "$DEPLOY_TEST_EVENTS"'

  install_backend_dependencies
  install_frontend_dependencies
  assert_file_line "$EVENTS" "pip-install" "first backend install must run"
  assert_file_line "$EVENTS" "npm-ci:https://registry.npmmirror.com" "npm install must use mirror"

  : > "$EVENTS"
  install_backend_dependencies
  install_frontend_dependencies
  [ ! -s "$EVENTS" ] || fail "unchanged dependencies should be skipped"

  rm -rf "$FAKE_ROOT/frontend/node_modules"
  install_frontend_dependencies
  assert_file_line "$EVENTS" "npm-ci:https://registry.npmmirror.com" \
    "missing node_modules must force npm ci"
}

run_frontend_staging_test() {
  make_fake_project
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  ROLLBACK_FRONTEND_DIR="$STATE_DIR/frontend-previous"
  FRONTEND_BUILD_COMMAND='mkdir -p "$DEPLOY_FRONTEND_OUT_DIR"; printf "<html>new</html>\\n" > "$DEPLOY_FRONTEND_OUT_DIR/index.html"'

  build_frontend_staged
  activate_frontend
  grep -Fq '<html>new</html>' "$FAKE_ROOT/frontend/dist/index.html" ||
    fail "successful staged build must become active"
  rollback_frontend
  grep -Fq '<html>old</html>' "$FAKE_ROOT/frontend/dist/index.html" ||
    fail "rollback must restore previous frontend"

  FRONTEND_BUILD_COMMAND='mkdir -p "$DEPLOY_FRONTEND_OUT_DIR"; exit 17'
  set +e
  build_frontend_staged >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "failed frontend build must return a nonzero status"
  grep -Fq '<html>old</html>' "$FAKE_ROOT/frontend/dist/index.html" ||
    fail "failed staged build must preserve active frontend"
}

run_orchestration_test() {
  make_fake_project
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  DEPLOY_TEST_EVENTS="$EVENTS"
  ensure_clean_git() { printf 'git-clean\n' >> "$DEPLOY_TEST_EVENTS"; }
  pull_source() { printf 'git-pull\n' >> "$DEPLOY_TEST_EVENTS"; }
  preflight() { printf 'preflight\n' >> "$DEPLOY_TEST_EVENTS"; }
  validate_production_config() { printf 'validate-config\n' >> "$DEPLOY_TEST_EVENTS"; }
  install_backend_dependencies() { printf 'backend-deps\n' >> "$DEPLOY_TEST_EVENTS"; }
  install_frontend_dependencies() { printf 'frontend-deps\n' >> "$DEPLOY_TEST_EVENTS"; }
  build_frontend_staged() { printf 'frontend-build\n' >> "$DEPLOY_TEST_EVENTS"; }
  backup_database_if_needed() { printf 'backup\n' >> "$DEPLOY_TEST_EVENTS"; }
  migrate_database() { printf 'migrate\n' >> "$DEPLOY_TEST_EVENTS"; }
  activate_frontend() { printf 'frontend-activate\n' >> "$DEPLOY_TEST_EVENTS"; }
  restart_backend() { printf 'restart\n' >> "$DEPLOY_TEST_EVENTS"; }
  wait_for_health() { printf 'health\n' >> "$DEPLOY_TEST_EVENTS"; }
  rollback_frontend() { printf 'frontend-rollback\n' >> "$DEPLOY_TEST_EVENTS"; }
  remember_previous_source() { printf 'remember-source\n' >> "$DEPLOY_TEST_EVENTS"; }
  rollback_source() { printf 'source-rollback\n' >> "$DEPLOY_TEST_EVENTS"; }

  run_update
  expected='git-clean
preflight
remember-source
git-pull
backend-deps
validate-config
frontend-deps
frontend-build
backup
migrate
restart
health
frontend-activate'
  [ "$(cat "$EVENTS")" = "$expected" ] || fail "update workflow order is incorrect"

  : > "$EVENTS"
  migrate_database() { printf 'migrate\n' >> "$DEPLOY_TEST_EVENTS"; return 29; }
  set +e
  run_update >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "migration failure must propagate"
  assert_file_missing_line "$EVENTS" "restart" "migration failure must prevent restart"

  : > "$EVENTS"
  migrate_database() { printf 'migrate\n' >> "$DEPLOY_TEST_EVENTS"; }
  wait_for_health() { printf 'health\n' >> "$DEPLOY_TEST_EVENTS"; return 31; }
  set +e
  run_update >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "health check failure must fail deployment"
  assert_file_missing_line "$EVENTS" "frontend-activate" \
    "health check failure must leave the existing frontend active"
  assert_file_missing_line "$EVENTS" "source-rollback" \
    "post-migration failure must retain source matching the new schema"

  : > "$EVENTS"
  wait_for_health() { printf 'health\n' >> "$DEPLOY_TEST_EVENTS"; }
  validate_production_config() { printf 'validate-config\n' >> "$DEPLOY_TEST_EVENTS"; return 32; }
  set +e
  run_update >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "pre-migration validation failure must fail deployment"
  assert_file_line "$EVENTS" "source-rollback" \
    "pre-migration failure must restore previous source"
  [ "$(grep -c '^backend-deps$' "$EVENTS")" -eq 2 ] ||
    fail "pre-migration rollback must restore dependencies for previous source"
}

run_init_backup_test() {
  make_fake_project
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  DEPLOY_TEST_EVENTS="$EVENTS"
  preflight() { :; }
  install_backend_dependencies() { :; }
  validate_production_config() { printf 'validate-config\n' >> "$DEPLOY_TEST_EVENTS"; }
  install_frontend_dependencies() { :; }
  build_frontend_staged() { :; }
  backup_database_if_needed() { printf 'backup\n' >> "$DEPLOY_TEST_EVENTS"; }
  migrate_database() { printf 'migrate\n' >> "$DEPLOY_TEST_EVENTS"; }
  activate_frontend() { :; }
  restart_backend() { printf 'restart\n' >> "$DEPLOY_TEST_EVENTS"; }
  wait_for_health() { printf 'health\n' >> "$DEPLOY_TEST_EVENTS"; }
  supervisor_is_configured() { return 0; }
  activate_frontend() { printf 'activate\n' >> "$DEPLOY_TEST_EVENTS"; }
  print_baota_guidance() { :; }

  run_init
  [ "$(cat "$EVENTS")" = $'validate-config\nbackup\nmigrate\nrestart\nhealth\nactivate' ] ||
    fail "init must back up, migrate, verify the backend, then activate the frontend"
}

run_database_probe_test() {
  make_fake_project
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  DEPLOY_TEST_EVENTS="$EVENTS"
  backup_database() { printf 'backup\n' >> "$DEPLOY_TEST_EVENTS"; }

  database_table_state() { printf 'populated\n'; }
  backup_database_if_needed
  assert_file_line "$EVENTS" "backup" "populated databases must be backed up"

  : > "$EVENTS"
  database_table_state() { printf 'empty\n'; }
  backup_database_if_needed >/dev/null
  [ ! -s "$EVENTS" ] || fail "empty databases should skip backup"

  database_table_state() { return 41; }
  set +e
  backup_database_if_needed >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "database inspection errors must abort deployment"
}

run_lock_and_cleanup_test() {
  make_fake_project
  source "$FAKE_ROOT/scripts/deploy-lib.sh"
  ROOT_DIR="$FAKE_ROOT"
  STATE_DIR="$FAKE_ROOT/var/deploy"
  DEPLOY_LOCK_DIR="$STATE_DIR/deploy.lock"
  DEPLOY_LOCK_HELD=0

  acquire_deploy_lock
  set +e
  (DEPLOY_LOCK_HELD=0; acquire_deploy_lock) >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "a concurrent deployment must be rejected"

  STAGED_FRONTEND_DIR="$STATE_DIR/frontend-releases/orphan"
  mkdir -p "$STAGED_FRONTEND_DIR"
  cleanup_deploy
  [ ! -e "$STAGED_FRONTEND_DIR" ] || fail "deployment cleanup must remove staged assets"
  [ ! -e "$DEPLOY_LOCK_DIR" ] || fail "deployment cleanup must release the lock"

  mkdir -p "$DEPLOY_LOCK_DIR"
  printf '99999999\n' > "$DEPLOY_LOCK_DIR/pid"
  acquire_deploy_lock
  [ "$(cat "$DEPLOY_LOCK_DIR/pid")" = "$$" ] || fail "stale deployment locks must be recovered"
  cleanup_deploy

  cat > "$FAKE_ROOT/signal-lock-test.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR='$FAKE_ROOT'
STATE_DIR='$STATE_DIR'
source '$FAKE_ROOT/scripts/deploy-lib.sh'
acquire_deploy_lock
trap cleanup_deploy EXIT
trap 'exit 143' TERM
while :; do sleep 1; done
EOF
  chmod +x "$FAKE_ROOT/signal-lock-test.sh"
  "$FAKE_ROOT/signal-lock-test.sh" &
  lock_test_pid=$!
  attempts=0
  while [ ! -f "$DEPLOY_LOCK_DIR/pid" ] && [ "$attempts" -lt 100 ]; do
    sleep 0.02
    attempts=$((attempts + 1))
  done
  kill -TERM "$lock_test_pid"
  set +e
  wait "$lock_test_pid"
  status=$?
  set -e
  [ "$status" -eq 143 ] || fail "TERM must stop deployment with status 143"
  [ ! -e "$DEPLOY_LOCK_DIR" ] || fail "TERM must release the deployment lock"
}

run_documentation_test() {
  local readme
  readme=$(cat "$PROJECT_ROOT/README.md")
  assert_contains "$readme" "./deploy.sh init" "README must document init"
  assert_contains "$readme" "./deploy.sh update" "README must document update"
  assert_contains "$readme" "var/deploy" "README must document deployment logs"
}

run_invalid_mode_test
run_dependency_test
run_frontend_staging_test
run_orchestration_test
run_init_backup_test
run_database_probe_test
run_lock_and_cleanup_test
run_documentation_test
printf 'deployment script tests: ok\n'
