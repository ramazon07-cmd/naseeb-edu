FROM python:3.12-slim

# APP_ENV=production makes the image fail closed: it refuses to boot without a
# real SECRET_KEY, PostgreSQL and persistent storage. docker-compose overrides it
# for local development.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

COPY . /app
WORKDIR /app/backend
# collectstatic needs no secrets; run it with build-only development settings.
RUN APP_ENV=development DEBUG=False python manage.py collectstatic --noinput

# Run as an unprivileged user. Upload directories are created here so mounted
# volumes inherit the right owner.
RUN groupadd --system --gid 10001 naseeb \
    && useradd --system --uid 10001 --gid naseeb --home-dir /app --shell /usr/sbin/nologin naseeb \
    && mkdir -p /app/backend/media /app/backend/private_documents \
    && chown -R naseeb:naseeb /app/backend/media /app/backend/private_documents
USER naseeb

EXPOSE 8000
# gthread workers: a slow request (e.g. a 35 s AI stream) holds one thread, not a
# whole worker. Tune WEB_CONCURRENCY (processes) and GUNICORN_THREADS per instance.
# Migrations belong in the deploy's pre-deploy step
# (`python manage.py migrate_locked --noinput`); MIGRATE_ON_START=1 runs them here
# instead, e.g. for docker-compose.
CMD ["sh", "-c", "if [ \"${MIGRATE_ON_START:-0}\" = 1 ]; then python manage.py migrate_locked --noinput || exit 1; fi; exec gunicorn core.wsgi:application --bind 0.0.0.0:${PORT:-8000} --worker-class gthread --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-8} --timeout 120 --graceful-timeout 30 --keep-alive 5 --max-requests ${GUNICORN_MAX_REQUESTS:-20000} --max-requests-jitter 2000 --access-logfile -"]
