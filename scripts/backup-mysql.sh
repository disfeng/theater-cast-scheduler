#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
mkdir -p "$BACKUP_DIR"
timestamp="$(date +%Y%m%d-%H%M%S)"
target="$BACKUP_DIR/${MYSQL_DATABASE}-${timestamp}.sql.gz"
defaults_file="$(mktemp)"
trap 'rm -f "$defaults_file"' EXIT
chmod 600 "$defaults_file"
printf '[client]\nhost=%s\nport=%s\nuser=%s\npassword=%s\n' "$MYSQL_HOST" "$MYSQL_PORT" "$MYSQL_USER" "$MYSQL_PASSWORD" > "$defaults_file"
migration="$(mysql --defaults-extra-file="$defaults_file" --batch --skip-column-names "$MYSQL_DATABASE" -e 'SELECT version_num FROM alembic_version' | tr '\n' ',')"
{
  printf '%s\n' "-- theater scheduler backup; migration=${migration%,}"
  mysqldump --defaults-extra-file="$defaults_file" --single-transaction --routines --triggers "$MYSQL_DATABASE"
} | gzip -c > "$target"
echo "$target"
