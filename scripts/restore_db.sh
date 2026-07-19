#!/usr/bin/env bash
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ] || [ -z "${1:-}" ]; then
  echo "Usage: DATABASE_URL=... ./scripts/restore_db.sh path/to/backup.dump"
  exit 1
fi

pg_restore --clean --if-exists --no-owner --no-acl --dbname "$DATABASE_URL" "$1"
echo "Database restore completed."
