#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
