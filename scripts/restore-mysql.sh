#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
backup="${1:?usage: restore-mysql.sh BACKUP.sql.gz --confirm}"
[[ "${2:-}" == "--confirm" ]] || { echo "restore requires --confirm" >&2; exit 2; }
[[ -f "$backup" ]] || { echo "backup file not found" >&2; exit 2; }
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"; MYSQL_PORT="${MYSQL_PORT:-3306}"
defaults_file="$(mktemp)"; trap 'rm -f "$defaults_file"' EXIT; chmod 600 "$defaults_file"
printf '[client]\nhost=%s\nport=%s\nuser=%s\npassword=%s\n' "$MYSQL_HOST" "$MYSQL_PORT" "$MYSQL_USER" "$MYSQL_PASSWORD" > "$defaults_file"
gzip -cd "$backup" | mysql --defaults-extra-file="$defaults_file" "$MYSQL_DATABASE"
echo "restore completed: $MYSQL_DATABASE"
