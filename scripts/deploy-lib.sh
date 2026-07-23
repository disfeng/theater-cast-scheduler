#!/usr/bin/env bash

ROOT_DIR=${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
STATE_DIR=${STATE_DIR:-$ROOT_DIR/var/deploy}
NPM_REGISTRY=${NPM_REGISTRY:-https://registry.npmmirror.com}
DEPLOY_API_URL=${DEPLOY_API_URL:-http://127.0.0.1:7004}
DEPLOY_RESTART_COMMAND=${DEPLOY_RESTART_COMMAND:-supervisorctl restart theaterops-api}
HEALTH_RETRIES=${HEALTH_RETRIES:-20}
HEALTH_RETRY_DELAY=${HEALTH_RETRY_DELAY:-2}
STAGED_FRONTEND_DIR=${STAGED_FRONTEND_DIR:-}
ROLLBACK_FRONTEND_DIR=${ROLLBACK_FRONTEND_DIR:-$STATE_DIR/frontend-previous}
PREVIOUS_SOURCE_COMMIT=${PREVIOUS_SOURCE_COMMIT:-}
DEPLOY_LOCK_DIR=${DEPLOY_LOCK_DIR:-$STATE_DIR/deploy.lock}
DEPLOY_LOCK_HELD=${DEPLOY_LOCK_HELD:-0}

mkdir -p "$STATE_DIR"
DEPLOY_LOG=${DEPLOY_LOG:-$STATE_DIR/deploy-$(date +%Y%m%d-%H%M%S).log}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$DEPLOY_LOG"
}

die() {
  log "ERROR: $*" >&2
  return 1
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

acquire_deploy_lock() {
  local holder stale_lock
  if ! mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null; then
    holder=''
    [ -f "$DEPLOY_LOCK_DIR/pid" ] && holder=$(cat "$DEPLOY_LOCK_DIR/pid")
    if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
      die "Another deployment is already running (pid: $holder)."
      return 1
    fi
    stale_lock="$DEPLOY_LOCK_DIR.stale.$$"
    if mv "$DEPLOY_LOCK_DIR" "$stale_lock" 2>/dev/null; then
      rm -rf "$stale_lock"
      log "Removed a stale deployment lock (pid: ${holder:-unknown})."
    fi
    mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null || {
      die "Another deployment acquired the lock while a stale lock was being recovered."
      return 1
    }
  fi
  printf '%s\n' "$$" > "$DEPLOY_LOCK_DIR/pid"
  DEPLOY_LOCK_HELD=1
}

cleanup_deploy() {
  if [ -n "${STAGED_FRONTEND_DIR:-}" ] && [ -d "$STAGED_FRONTEND_DIR" ]; then
    rm -rf "$STAGED_FRONTEND_DIR"
  fi
  if [ "${DEPLOY_LOCK_HELD:-0}" = 1 ]; then
    rm -rf "$DEPLOY_LOCK_DIR"
    DEPLOY_LOCK_HELD=0
  fi
}

preflight() {
  local command
  for command in git python3 npm curl; do
    have_command "$command" || die "Required command not found: $command" || return
  done
  [ -f "$ROOT_DIR/backend/.env" ] ||
    die "Missing backend/.env. Copy backend/.env.example and configure production values first." || return
  [ -f "$ROOT_DIR/backend/pyproject.toml" ] || die "Missing backend/pyproject.toml" || return
  [ -f "$ROOT_DIR/frontend/package-lock.json" ] || die "Missing frontend/package-lock.json" || return
}

hash_file() {
  if have_command sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  elif have_command shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "Neither sha256sum nor shasum is available"
  fi
}

fingerprint_matches() {
  local source_file=$1
  local state_file=$2
  [ -f "$state_file" ] && [ "$(cat "$state_file")" = "$(hash_file "$source_file")" ]
}

write_fingerprint() {
  local source_file=$1
  local state_file=$2
  local temporary="$state_file.tmp.$$"
  hash_file "$source_file" > "$temporary"
  mv "$temporary" "$state_file"
}

run_configured_command() {
  local configured=$1
  shift
  if [ -n "$configured" ]; then
    eval "$configured"
  else
    "$@"
  fi
}

install_backend_dependencies() {
  local project_file="$ROOT_DIR/backend/pyproject.toml"
  local fingerprint="$STATE_DIR/backend-dependencies.sha256"
  if [ -x "$ROOT_DIR/backend/.venv/bin/python" ] && fingerprint_matches "$project_file" "$fingerprint"; then
    log "Backend dependencies unchanged; skipping pip install."
    return
  fi

  log "Installing backend dependencies..."
  if [ ! -x "$ROOT_DIR/backend/.venv/bin/python" ]; then
    python3 -m venv "$ROOT_DIR/backend/.venv"
  fi
  (
    cd "$ROOT_DIR/backend"
    run_configured_command "${PIP_INSTALL_COMMAND:-}" \
      .venv/bin/pip install --disable-pip-version-check -e .
  )
  write_fingerprint "$project_file" "$fingerprint"
}

warn_stale_npm_config() {
  local global_config
  global_config=$(npm config get globalconfig 2>/dev/null || true)
  if [ -f "$global_config" ] && grep -Eq '^--init\.module[[:space:]]*=' "$global_config"; then
    log "npm global config contains invalid --init.module. Remove that line from: $global_config"
  fi
}

install_frontend_dependencies() {
  local lock_file="$ROOT_DIR/frontend/package-lock.json"
  local fingerprint="$STATE_DIR/frontend-dependencies.sha256"
  if [ -d "$ROOT_DIR/frontend/node_modules" ] && fingerprint_matches "$lock_file" "$fingerprint"; then
    log "Frontend dependencies unchanged; skipping npm ci."
    return
  fi

  log "Installing frontend dependencies from $NPM_REGISTRY..."
  warn_stale_npm_config
  (
    cd "$ROOT_DIR/frontend"
    run_configured_command "${NPM_CI_COMMAND:-}" npm ci \
      --registry="$NPM_REGISTRY" --prefer-offline --no-audit --no-fund
  )
  write_fingerprint "$lock_file" "$fingerprint"
}

build_frontend_staged() {
  STAGED_FRONTEND_DIR=${STAGED_FRONTEND_DIR:-$STATE_DIR/frontend-releases/release-$(date +%Y%m%d-%H%M%S)-$$}
  rm -rf "$STAGED_FRONTEND_DIR"
  mkdir -p "$STAGED_FRONTEND_DIR"
  log "Building frontend into staging directory..."
  export DEPLOY_FRONTEND_OUT_DIR="$STAGED_FRONTEND_DIR"
  if [ -n "${FRONTEND_BUILD_COMMAND:-}" ]; then
    (cd "$ROOT_DIR/frontend" && eval "$FRONTEND_BUILD_COMMAND")
  else
    (
      cd "$ROOT_DIR/frontend"
      ./node_modules/.bin/vue-tsc --noEmit
      ./node_modules/.bin/vite build --outDir "$STAGED_FRONTEND_DIR" --emptyOutDir
    )
  fi
  [ -f "$STAGED_FRONTEND_DIR/index.html" ] ||
    die "Frontend build did not produce index.html" || return
  (cd "$STAGED_FRONTEND_DIR" && find . -type f -print | LC_ALL=C sort) > \
    "$STAGED_FRONTEND_DIR/.deploy-manifest"
}

prune_active_frontend() {
  local active=$1
  local manifest="$STATE_DIR/frontend-current-manifest"
  local file relative
  [ -f "$manifest" ] || return 0
  while IFS= read -r -d '' file; do
    relative=".${file#"$active"}"
    [ "$relative" = "./index.html" ] && continue
    grep -Fqx "$relative" "$manifest" || rm -f "$file"
  done < <(find "$active" -type f -print0)
  find "$active" -depth -type d -empty -delete
}

activate_frontend() {
  local active="$ROOT_DIR/frontend/dist"
  local item
  local temporary_index="$active/.index-next.$$"
  [ -f "$STAGED_FRONTEND_DIR/index.html" ] || die "No staged frontend is available" || return
  mkdir -p "$active"
  prune_active_frontend "$active"
  rm -rf "$ROLLBACK_FRONTEND_DIR"
  rm -f "$STATE_DIR/frontend-previous-manifest"
  if [ -f "$STATE_DIR/frontend-current-manifest" ]; then
    cp "$STATE_DIR/frontend-current-manifest" "$STATE_DIR/frontend-previous-manifest"
  fi
  if [ -d "$active" ]; then
    cp -a "$active" "$ROLLBACK_FRONTEND_DIR"
  fi
  for item in "$STAGED_FRONTEND_DIR"/*; do
    [ "$(basename "$item")" = "index.html" ] && continue
    cp -a "$item" "$active/"
  done
  cp "$STAGED_FRONTEND_DIR/index.html" "$temporary_index"
  python3 - "$temporary_index" "$active/index.html" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
  cp "$STAGED_FRONTEND_DIR/.deploy-manifest" "$STATE_DIR/frontend-current-manifest.tmp.$$"
  mv "$STATE_DIR/frontend-current-manifest.tmp.$$" "$STATE_DIR/frontend-current-manifest"
  rm -rf "$STAGED_FRONTEND_DIR"
  STAGED_FRONTEND_DIR=''
  log "Frontend assets activated."
}

rollback_frontend() {
  local active="$ROOT_DIR/frontend/dist"
  local item
  local temporary_index="$active/.index-rollback.$$"
  [ -f "$ROLLBACK_FRONTEND_DIR/index.html" ] || return 0
  for item in "$ROLLBACK_FRONTEND_DIR"/*; do
    [ "$(basename "$item")" = "index.html" ] && continue
    cp -a "$item" "$active/"
  done
  cp "$ROLLBACK_FRONTEND_DIR/index.html" "$temporary_index"
  python3 - "$temporary_index" "$active/index.html" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
  if [ -f "$STATE_DIR/frontend-previous-manifest" ]; then
    cp "$STATE_DIR/frontend-previous-manifest" "$STATE_DIR/frontend-current-manifest"
  else
    rm -f "$STATE_DIR/frontend-current-manifest"
  fi
  log "Previous frontend assets restored."
}

validate_production_config() {
  log "Validating production configuration before database changes..."
  (cd "$ROOT_DIR/backend" && APP_ENV=production .venv/bin/python -c \
    'from app.core.config import settings; settings.validate_runtime_safety()')
}

ensure_clean_git() {
  [ -z "$(git -C "$ROOT_DIR" status --porcelain)" ] ||
    die "Git working tree has tracked changes; commit or restore them before deployment." || return
}

remember_previous_source() {
  PREVIOUS_SOURCE_COMMIT=$(git -C "$ROOT_DIR" rev-parse HEAD)
}

rollback_source() {
  [ -n "$PREVIOUS_SOURCE_COMMIT" ] || return 0
  log "Restoring source commit $PREVIOUS_SOURCE_COMMIT..."
  git -C "$ROOT_DIR" reset --hard "$PREVIOUS_SOURCE_COMMIT"
}

pull_source() {
  log "Updating source from origin/main..."
  git -C "$ROOT_DIR" pull --ff-only origin main
}

write_database_backup_env() {
  local target=$1
  (cd "$ROOT_DIR/backend" && .venv/bin/python - "$target" <<'PY'
import shlex
import sys

from sqlalchemy.engine import make_url

from app.core.config import settings

url = make_url(settings.database_url)
if not url.drivername.startswith("mysql"):
    raise SystemExit("Production backup requires a MySQL DATABASE_URL")
values = {
    "MYSQL_HOST": url.host or "127.0.0.1",
    "MYSQL_PORT": str(url.port or 3306),
    "MYSQL_DATABASE": url.database or "",
    "MYSQL_USER": url.username or "",
    "MYSQL_PASSWORD": url.password or "",
}
if not values["MYSQL_DATABASE"] or not values["MYSQL_USER"]:
    raise SystemExit("DATABASE_URL must include database and username")
with open(sys.argv[1], "w", encoding="utf-8") as output:
    for key, value in values.items():
        output.write(f"{key}={shlex.quote(value)}\n")
PY
  )
}

database_table_state() {
  (cd "$ROOT_DIR/backend" && .venv/bin/python - <<'PY'
from sqlalchemy import inspect

from app.db.session import engine

print("populated" if inspect(engine).get_table_names() else "empty")
PY
  )
}

backup_database() {
  local exports_file="$STATE_DIR/database-backup-env.$$"
  (
    umask 077
    trap 'rm -f "$exports_file"' EXIT
    write_database_backup_env "$exports_file"
    chmod 600 "$exports_file"
    # This file is generated by Python with shell-escaped values; it is not the user-authored .env.
    # shellcheck disable=SC1090
    source "$exports_file"
    export MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD
    log "Backing up database before migration..."
    BACKUP_DIR="$STATE_DIR/backups" "$ROOT_DIR/scripts/backup-mysql.sh" | tee -a "$DEPLOY_LOG"
  )
}

backup_database_if_needed() {
  local state
  state=$(database_table_state) || {
    die "Unable to inspect the database; refusing to migrate without a verified backup state."
    return 1
  }
  case "$state" in
    populated) backup_database ;;
    empty) log "Database is empty; no pre-migration backup is required." ;;
    *) die "Unexpected database inspection result: $state" ; return 1 ;;
  esac
}

migrate_database() {
  log "Applying database migrations..."
  (cd "$ROOT_DIR/backend" && .venv/bin/alembic upgrade head)
  (cd "$ROOT_DIR/backend" && .venv/bin/alembic current --check-heads >/dev/null)
}

restart_backend() {
  log "Restarting backend..."
  eval "$DEPLOY_RESTART_COMMAND"
}

wait_for_endpoint() {
  local path=$1
  local attempt=1
  while [ "$attempt" -le "$HEALTH_RETRIES" ]; do
    if curl --fail --silent --show-error "$DEPLOY_API_URL$path" >/dev/null; then
      return 0
    fi
    sleep "$HEALTH_RETRY_DELAY"
    attempt=$((attempt + 1))
  done
  die "Health check failed: $DEPLOY_API_URL$path"
}

wait_for_health() {
  log "Waiting for backend health checks..."
  wait_for_endpoint /health
  wait_for_endpoint /ready
  log "Backend health checks passed."
}

supervisor_is_configured() {
  if [ -n "${DEPLOY_FORCE_RESTART:-}" ]; then
    return 0
  fi
  have_command supervisorctl && supervisorctl status theaterops-api >/dev/null 2>&1
}

print_baota_guidance() {
  cat <<EOF

Application build is ready.

Baota Supervisor:
  Name: theaterops-api
  Directory: $ROOT_DIR
  Command: $ROOT_DIR/scripts/start-production.sh
  User: www

Nginx site root:
  $ROOT_DIR/frontend/dist

API proxy:
  location /api/ { proxy_pass http://127.0.0.1:7004/; }

Deployment log:
  $DEPLOY_LOG
EOF
}

run_init() {
  preflight || return
  install_backend_dependencies || return
  validate_production_config || return
  install_frontend_dependencies || return
  build_frontend_staged || return
  backup_database_if_needed || return
  migrate_database || return
  if supervisor_is_configured; then
    if ! restart_backend; then
      log "Backend restart failed after migration; retrying the new release once."
      restart_backend || return
    fi
    wait_for_health || return
  else
    log "Supervisor program theaterops-api is not configured yet; restart and health check skipped."
  fi
  activate_frontend || return
  print_baota_guidance
}

run_update() {
  ensure_clean_git || return
  preflight || return
  remember_previous_source || return
  pull_source || return
  if ! install_backend_dependencies ||
    ! validate_production_config ||
    ! install_frontend_dependencies ||
    ! build_frontend_staged ||
    ! backup_database_if_needed; then
    rollback_source || true
    install_backend_dependencies ||
      log "WARNING: source was restored but previous backend dependencies could not be restored."
    return 1
  fi

  # Database migrations are forward-only. After this point the new source remains checked out,
  # because an older release may reject or misunderstand the new Alembic head.
  migrate_database || return
  if ! restart_backend; then
    log "Backend restart failed after migration; retrying the new release once."
    restart_backend || true
    return 1
  fi
  wait_for_health || return
  activate_frontend || return
  log "Deployment completed successfully."
}
