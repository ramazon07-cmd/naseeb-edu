# Naseeb Edu Backend

Django + Django REST Framework + JWT + Swagger.

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000 --noreload
```

## Reset demo

```bash
python manage.py reset_demo
```

## Local demo login

```text
Counselor:
username: counselor
password: admin12345

Organization School:
username: schooladmin
password: school12345

Student:
username: ramazon
password: student12345
```

These accounts are only available when `ENABLE_DEMO_ACCOUNTS=True`. Production must use `APP_ENV=production`, `DEBUG=False`, `ENABLE_DEMO_ACCOUNTS=False`, a unique `SECRET_KEY`, and an external PostgreSQL `DATABASE_URL`; see `.env.production.example`.

## API Docs

```text
http://127.0.0.1:8000/api/docs/
```
