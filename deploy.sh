#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/deploy-lib.sh
source "$ROOT_DIR/scripts/deploy-lib.sh"

usage() {
  cat <<'EOF'
Usage: ./deploy.sh <init|update>

  init    Install dependencies, migrate the database, and build production assets.
  update  Pull main, install changed dependencies, back up and migrate the database,
          atomically replace frontend assets, restart the API, and verify health.
EOF
}

case "${1:-}" in
  init)
    acquire_deploy_lock
    trap cleanup_deploy EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    run_init
    ;;
  update)
    acquire_deploy_lock
    trap cleanup_deploy EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    run_update
    ;;
  -h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
