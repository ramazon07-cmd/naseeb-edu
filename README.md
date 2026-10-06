# Naseeb Edu — Education Counseling Platform

Production-oriented CRM for schools and counselors managing students who apply to international universities. The frontend is React 19 + Vite and installs reproducibly with `npm ci`.

## Roles

| Role | Access |
| --- | --- |
| Admin | Product staff (tiers: support, ops, super admin). Provisions schools, counselors and plans, opens Student 360 for any student, reads the audit log and handles support |
| Organization School | Its own school's students: create and edit them, read-only Student 360, meetings and messages |
| Counselor | Only the students assigned to them: review queue, Student 360, essays, applications, documents, meetings and messages; invites parents |
| Teacher | Students in their own school; creates Tasks and Roadmap missions and approves submitted work |
| Student | Their own profile, assessment, roadmap, tasks, applications, documents, essays, meetings and messages |
| Parent | Read-only view of linked children (progress, tasks, applications, documents, meetings) once they accept a counselor's invite |

Public registration is disabled. Students are created by a counselor or their school; parents join through an invite.

## Brand and themes

This section is the single description of the palette; the tokens themselves
live in `frontend/src/styles.css` (`:root` for light, `:root[data-theme='dark']`
for dark), and components use the semantic tokens (`--canvas`, `--surface`,
`--text`, `--accent`…), never raw colors.

- Official identity: Naseeb Edu — “Bridging Uzbekistan to the World Through Education”.
- The theme toggle is available on both login and authenticated pages. The first visit follows the OS preference (`prefers-color-scheme`); the choice is then kept in local storage (`naseeb-edu-theme`).

| Theme | Role | Token | Value |
| --- | --- | --- | --- |
| Light | Ivory Paper | `--ivory` | `#f5f0e6` |
| Light | Warm Taupe (accent) | `--taupe`, `--accent` | `#b8a58a` |
| Light | Deep Ink (text, active nav) | `--deep-ink`, `--text` | `#4a4036` |
| Light | Soft Shadow | `--soft-shadow` | `#d8cec0` |
| Light | Canvas / surface | `--canvas`, `--surface` | `#f7f7f7`, `#ffffff` |
| Dark | Midnight canvas / surface | `--canvas`, `--surface` | `#10202d`, `#162936` |
| Dark | Ice-blue accent | `--accent` | `#9fc6e2` |
| Dark | Silver | `--silver` | `#c5d0d8` |
| Dark | Charcoal | `--charcoal` | `#0c1923` |
| Dark | Text | `--text` | `#f7f7f7` |

## Features

- Interface in Uzbek, Russian and English (`frontend/src/translations`); API errors follow `Accept-Language`
- Role-specific dashboards, navigation and data isolation per school and per assigned counselor
- Student Center: academics, test scores, portfolio (projects, internships, research), activities, honors, certificates and documents
- Profile Assessment challenges that suggest best-fit study directions
- Roadmap missions and Tasks with deadlines, submissions and staff approval; approval-backed XP and level-ups
- Counselor Review queue and Student 360 view
- University application tracker, College Search (filters, shortlist, scholarships) and a Programs catalog of national and international opportunities
- Essay Lab: drafts, revision history, sharing and counselor feedback; optional AI checks under the plan's `essay_coach` feature
- Documents with private file storage and review; Google Docs links with previews
- Meetings scheduler with counselor availability and booking requests
- Messages: direct chats, groups, school communities and discussions, with reports and moderation
- Notifications bell, Screen Time (active learning time), Support tickets and account settings
- Parent portal, workspace plans and subscriptions (read-only when lapsed), audit log
- Naseeb AI assistant for students and counselors; it and every other outside AI call (Essay Coach AI checks, education guidance) are **off by default** (`AI_ASSISTANT_ENABLED`, see `backend/README.md`)
- Naseeb Store (sample offers; locked for students for now)
- Django Admin and OpenAPI/Swagger docs

## Local demo accounts

Run `python manage.py seed_demo` first.

```text
Counselor:    counselor   / admin12345
Organization: schooladmin / school12345
Student:      ramazon     / student12345
Parent:       parent      / parent12345
```

Demo accounts are development-only. They are enabled by `ENABLE_DEMO_ACCOUNTS=True`, and their local passwords can be replaced with the `DEMO_*_PASSWORD` variables in `backend/.env`. Create an admin with `python manage.py createsuperuser`.

## Quick local start

Terminal 1:

```bash
./scripts/start_backend.sh
```

Terminal 2:

```bash
./scripts/start_frontend.sh
```

Open:

- React app: `http://127.0.0.1:5173/`
- API docs: `http://127.0.0.1:8000/api/docs/`
- Healthcheck: `http://127.0.0.1:8000/api/health/`
- Django Admin: `http://127.0.0.1:8000/admin/`

## Manual setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

In a second terminal:

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

The frontend uses `VITE_API_URL` and defaults to `http://127.0.0.1:8000/api`.

## Docker start

```bash
docker compose up --build
```

This starts PostgreSQL, Django/Gunicorn and the Nginx-served React frontend at `http://127.0.0.1:3000`.

## Tests

```bash
# Backend (from backend/, with the venv active)
SECRET_KEY=dev-only DEBUG=True ALLOWED_HOSTS=localhost,testserver python manage.py test --parallel

# Frontend (from frontend/)
npm test          # node --test unit tests
npm run lint
npm run build
node ../scripts/frontend_smoke.js
```

`./scripts/verify.sh` runs Django checks, migration-drift detection, the backend tests, the frontend build and the smoke checks in one go. CI (`.github/workflows/ci.yml`) runs the backend tests on SQLite and PostgreSQL plus the frontend lint, tests, audit, build and i18n smoke checks.

## Production environment

Required:

```env
APP_ENV=production
SECRET_KEY=long-random-production-secret
DEBUG=False
ALLOWED_HOSTS=api.example.com
CORS_ALLOWED_ORIGINS=https://app.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
DATABASE_URL=postgresql://user:password@host:5432/database
ENABLE_DEMO_ACCOUNTS=False
STORAGE_BACKEND=s3
AWS_STORAGE_BUCKET_NAME=naseeb-files
AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
AWS_S3_REGION_NAME=auto
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
DOCUMENT_MAX_UPLOAD_SIZE=26214400
```

Start from `backend/.env.production.example` and `frontend/.env.production.example`. Store the real values in the deployment provider's secret manager; do not upload or commit a real `.env` file.

Production startup fails early when `DEBUG=True`, the secret key is missing/weak, `DATABASE_URL` is missing or points to SQLite, or demo accounts are enabled. When demo accounts are disabled, `seed_demo` safely exits without writing data and `reset_demo` remains blocked before any flush. Local `.env`, SQLite files, media, virtual environments, build output and dependencies are excluded from Git, Docker build context and release ZIP files.

Production deployment must use PostgreSQL and private object storage for uploads. With `STORAGE_BACKEND=s3` every upload goes to a private S3-compatible bucket (AWS S3 or Cloudflare R2); nothing is written to the instance disk, so the web service can run several instances. The bucket must block public access: student documents, evidence, photos and avatars reach users only through their authenticated API endpoints, which stream photos and avatars and hand out presigned URLs for everything else that expire after `PRIVATE_FILE_URL_EXPIRE_SECONDS` (60 by default). Production startup refuses local-disk storage unless `FILE_STORAGE_SINGLE_INSTANCE=True` acknowledges a single instance; then `MEDIA_ROOT` and `DOCUMENT_STORAGE_ROOT` must be persistent volumes, included in backups and never exposed through Nginx or a public `/media/` route. Bucket setup, CORS and the one-off copy of existing files (`migrate_files_to_object_storage`) are described in `docs/scaling.md` under "File storage". The included Docker Compose configuration (development) mounts separate `media_data` and `private_document_data` volumes. The included `Procfile`, `build.sh`, `Dockerfile`, healthcheck and Gunicorn configuration support common container or PaaS deployments.

For Render, connect `DATABASE_URL` to one persistent Render PostgreSQL database and keep that same database attached across deploys. Set `APP_ENV=production`, `DEBUG=False`, and `ENABLE_DEMO_ACCOUNTS=False`; Render's hosted-runtime guard refuses to boot with the ephemeral development SQLite fallback. Use `./build.sh` as the build command, `cd backend && python manage.py migrate_locked --noinput` as the pre-deploy command and the `Procfile` web command (or its equivalent) as the start command; `render.yaml` defines the scheduled jobs. See `docs/scaling.md` for the full Render checklist. Never use `reset_and_start_backend.sh`, `reset_demo`, or `flush` in a Render build, pre-deploy, or start command. The Render persistent disk stores uploaded files only; it does not replace PostgreSQL. Take a PostgreSQL backup before changing `DATABASE_URL` or deleting/recreating the database service.

Create a clean handoff ZIP without `.env`, SQLite, uploaded media, virtual environments, dependencies or compiled output:

```bash
./scripts/package_release.sh
```

## Project structure

```text
naseeb-edu/
├── backend/
│   ├── apps/users/
│   ├── apps/admissions/
│   ├── core/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── package-lock.json
│   └── Dockerfile
├── scripts/
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
└── Procfile
```
