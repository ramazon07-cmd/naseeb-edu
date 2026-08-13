#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

python manage.py migrate --noinput
python manage.py runserver 127.0.0.1:8000 --noreload
