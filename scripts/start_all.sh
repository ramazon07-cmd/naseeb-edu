#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

osascript >/dev/null 2>&1 <<APPLESCRIPT || true
tell application "Terminal"
  do script "cd '$ROOT' && ./scripts/start_backend.sh"
  do script "cd '$ROOT' && ./scripts/start_frontend.sh"
  activate
end tell
APPLESCRIPT

cat <<EOF
Naseeb Edu starting...
Backend:  http://127.0.0.1:8000/api/docs/
Frontend: http://127.0.0.1:5173/
Login:    counselor / admin12345

If Terminal windows did not open, run these manually:
  ./scripts/start_backend.sh
  ./scripts/start_frontend.sh
EOF
