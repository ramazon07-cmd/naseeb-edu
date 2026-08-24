#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/naseeb-schema.yaml
python manage.py test -v 2
cd "$ROOT/frontend"
npm ci
npm run build
cd "$ROOT"
node scripts/frontend_smoke.js
node scripts/i18n_audit.mjs
echo "All Naseeb Edu checks passed."
