#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate_locked --noinput
# The QS rankings ship as snapshots in the repo. Both loaders are idempotent (a second run changes nothing, about
# 2 s each on the full catalogue), so every deploy brings the catalogue up to date. A failure stops the deploy,
# like a failed migration. The subject loader needs the QS universities, hence this order.
python manage.py load_qs_rankings
python manage.py load_qs_subject_rankings
