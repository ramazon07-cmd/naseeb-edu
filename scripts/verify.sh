#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# Local checks run in development mode unless the caller chose otherwise; a
# missing APP_ENV would otherwise fail closed to production.
export APP_ENV="${APP_ENV:-development}"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test -v 2
cd "$ROOT/frontend"
npm ci
npm run build
cd "$ROOT"
node scripts/frontend_smoke.js
echo "All Naseeb Edu checks passed."
