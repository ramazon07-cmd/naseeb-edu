#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-$ROOT/Naseeb-Edu-Production.zip}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
mkdir -p "$STAGE/Naseeb-Edu-Production"
rsync -a \
  --exclude '.git/' \
  --include '.env.example' \
  --include '.env.production.example' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.venv/' \
  --exclude '.audit-venv/' \
  --exclude 'node_modules/' \
  --exclude 'dist/' \
  --exclude 'db.sqlite3' \
  --exclude '*.sqlite3' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'staticfiles/' \
  --exclude 'media/' \
  --exclude '.DS_Store' \
  --exclude 'Naseeb-Edu-Production*.zip' \
  "$ROOT/" "$STAGE/Naseeb-Edu-Production/"

(cd "$STAGE" && zip -qr "$OUTPUT" Naseeb-Edu-Production)

BAD_FILES="$(unzip -Z1 "$OUTPUT" \
  | grep -E '(^|/)(node_modules|\.venv|\.audit-venv|dist|__pycache__|staticfiles|media)(/|$)|(^|/)\.env($|\.)|(^|/)(db\.)?[^/]*\.sqlite3$|\.pyc$' \
  | grep -Ev '/\.env(\.production)?\.example$' || true)"
if [ -n "$BAD_FILES" ]; then
  echo 'Release validation failed: a private or generated file was included.' >&2
  echo "$BAD_FILES" >&2
  exit 1
fi

unzip -tq "$OUTPUT"
echo "Clean release created: $OUTPUT"
