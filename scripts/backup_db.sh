#!/usr/bin/env bash
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required."
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/rbis-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" --file "$FILE"
pg_restore --list "$FILE" >/dev/null
echo "Verified backup created: $FILE"
