#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/scripts/check-production-config.sh"
cd "$ROOT_DIR/backend"
exec .venv/bin/uvicorn app.main:app --host "${APP_HOST:-127.0.0.1}" --port "${APP_PORT:-7004}" --workers "${APP_WORKERS:-2}"
