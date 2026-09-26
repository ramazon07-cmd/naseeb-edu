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

If `APP_ENV` is not set, the backend fails closed to production (it refuses to start without real secrets) unless `DEBUG=True` is set explicitly on a non-hosted machine or the test runner is used. There is no built-in default `SECRET_KEY`; development without one gets a random per-process key.

## API Docs

```text
http://127.0.0.1:8000/api/docs/
```

## Programs and Store catalog (2026-09-20)

Deploy normally with `python manage.py migrate --noinput` against the deployment's
own `DATABASE_URL`. Migrations 0034/0035 add the catalog fields and a frozen data
snapshot, so production gets the same catalog from its own database. Both `build.sh`
and the production start command run migrations; never copy the local SQLite file
and never run `seed_demo` in production.

### Programs

`migrations/catalog_data/portal_catalog_20260920.json` holds 154 programs from two
kinds of source, each tagged by its `source_key` prefix:

- `sheet-` (101): the counselor spreadsheet, grade 5-11 tabs plus `deadline`,
  `Summer programs` and `Sheet10`. `scripts/build_program_catalog.py` regenerates
  exactly these rows from an `export?format=xlsx` download of the sheet and leaves
  every other row untouched.
- `pdf-` (53): three counselor PDF compilations (extracurricular opportunities for
  Uzbek high school students, the High School Programs list, and the summer program
  list). Only facts were taken: name, official link, the funding note and deadline
  text where the document prints them per programme, and `eligible_grades = 9,10,11`
  because each document states it lists high school opportunities. The PDFs' own
  descriptions, cost tables and 2023/24 cycle dates were left out: their text layer
  interleaves those across page blocks, so they cannot be attached to the right
  programme with confidence. Duplicates across the sheet and the PDFs are dropped on
  normalised title or identical application link. Every imported link was requested
  once: three deep links were replaced by the working parent page, and Google Code
  Jam and Kick Start were left out because Google ended both and the pages are gone.
  48 Hour Film Race, NobelIntern and StartUp Initiatives are kept even though their
  TLS handshake fails from outside Uzbekistan; confirm them before a student relies
  on them.

Ship a refreshed list as a new migration, not by editing one that has already run.
The spreadsheet was read only and was not modified. Per program the snapshot keeps the
sheet's own age range, the grades of every tab it appears on, the raw application
open/close text, the link, and the sheet/row it came from in `source_metadata`.

Only the eight `Sheet10` rows carry a real `deadline` date (`dd.mm.yyyy`). Every other
row keeps its text in `deadline_text` with `needs_verification=True`, and the UI shows
it as "Usual deadline ... confirm the date" instead of inventing a date. Programs whose
dated deadline has passed stay in the catalog, are labelled as closed and are hidden
behind the "Hide N closed" filter, because most of these programs repeat every year.

The loader is idempotent: it skips a `source_key` that already exists, and it skips
any program whose title already exists as a hand-curated record without a `source_key`,
so admin edits are never overwritten. Re-running it imports nothing new.

### Store

The four Store offers intentionally contain **sample prices and placeholder provider
names**; the UI labels them as samples. Edit `StoreItem` in Django admin to set the
real provider, price, currency, duration and deliverables, then clear `is_sample` once
the details are confirmed. Keyed records are never overwritten by a re-run, real offers
are preserved, and the reverse migration does not delete catalog records.

## Migrations

- Deploys run `python manage.py migrate_locked --noinput` (Procfile, Dockerfile, `build.sh`). On PostgreSQL it takes an advisory lock, so several instances booting at once apply migrations one at a time instead of racing; on SQLite it is plain `migrate`. On Render you can also move it to a pre-deploy command and drop it from the start command.
- The admissions history (`0001`–`0037`) is intentionally **not** squashed: several migrations move private files on disk and cannot be reversed, and a squash would have to be verified against every production database first. New migrations should stay reversible where possible and must never move files without a documented manual rollback.

## API error conventions

- Every error response is JSON with a top-level human-readable `detail`; field validation errors are kept alongside it (`{"detail": "...", "email": ["..."]}`). Errors are localized from `Accept-Language` (uz/ru/en).
- `400` invalid input (including non-numeric id parameters), `401` not authenticated, `403` authenticated but not allowed to perform the action, `404` the object does not exist *or is outside your scope* (the API does not reveal which), `409` the request conflicts with the current state (e.g. roadmap not active, duplicate active roadmap), `413` request body too large, `429` throttled or locked out.
