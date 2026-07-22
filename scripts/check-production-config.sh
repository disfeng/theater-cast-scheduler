#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"
APP_ENV=production .venv/bin/python -c 'from app.core.config import settings; settings.validate_runtime_safety(); print("production configuration: ok")'
.venv/bin/alembic current --check-heads >/dev/null
echo "database migration: current"
