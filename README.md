# Naseeb Edu — Education Counseling Platform

Production-oriented CRM for schools and counselors managing students who apply to international universities. The frontend is React 19 + Vite and installs reproducibly with `npm ci`.

## Roles

| Role | Access |
| --- | --- |
| School Counselor | Only students assigned to that counselor, including their tasks and responses, college list, documents, essays, portfolio records, recommendations and meetings |
| Teacher | Students in their own school; creates and controls Tasks and Roadmap missions, and approves submitted work |
| Organization School | Its own students only; student create/edit/delete plus read-only Student 360° admissions records |
| Student | Only the signed-in student's profile, assigned tasks, academics, projects, internships, activities, honors, recommendations, applications, documents, certificates, essays and counselor meetings |

Public registration is disabled. Students are created by a counselor or their school organization.

## Brand and themes

- Official identity: Naseeb Edu — “Bridging Uzbekistan to the World Through Education”.
- Light mode uses the warm ivory/taupe Naseeb Edu system; dark mode uses the purple/silver logo.
- The theme toggle is available on both login and authenticated pages, follows the first OS preference, and persists in local storage.
- The student light interface uses warm ivory, taupe and brown surfaces; dark mode keeps the Deep Purple, Silver and Charcoal identity.

## Included modules

- Schools and organization accounts
- Student academic profiles: GPA, IELTS, SAT, major, countries, budget and scholarship requirement
- Teacher/counselor-controlled Tasks with deadlines, priorities, student submission and staff approval
- University application tracker with dream/target/safety tiers
- Documents with real file upload and counselor review
- Essays and personal statement review
- Achievements, research, projects, internships, activities and honors
- Recommendation-letter workflow
- Counselor meeting notes, notifications and activity logs
- Student 360° profile for counselors and school organizations, with assigned tasks and full student responses, college list, essays, files and every admissions section in one view
- Google Docs integration for task submissions, student documents and essays, including validated links, embedded visual previews and direct “Open in Google Docs” actions
- Dedicated student Certificates and Meetings pages
- Student portal dashboard and Student Center with academic, portfolio, activity and document tabs
- Teacher/counselor-controlled Roadmap missions, task list and timeline; student progress, submission and reflections; staff approval
- Duolingo-style student Roadmap path with live mission states, responsive light/dark themes, XP progress and the next level checkpoint
- Approval-backed XP and Leveling: approved Tasks award 25/50/75/100 XP by priority, approved Roadmap missions award 75 XP, and every award is recorded once in an XP ledger
- Level thresholds grow cumulatively (Level 2 at 100 XP, Level 3 at 300 XP, Level 4 at 600 XP); reaching a threshold creates a pending level-up that only a teacher/counselor can approve
- Scalable messaging for every role: unique private Direct conversations, invite-only Groups, joinable school Communities and Stack Overflow-style Discussions with threaded replies, anonymous mode, unread counts and accepted answers
- Confidential message reports with duplicate/self-report protection and a school-scoped moderation queue; trusted admins, counselors, teachers and school organizations can review/dismiss reports, remove content or mute a channel member for 24 hours/7 days while anonymous identity stays hidden in the normal feed
- Counselor and school messaging interfaces add scoped contacts, inbox/report metrics, audience shortcuts and channel-member management
- Fixed corner notification center for students, counselors and school organizations, with unread counts and mark-as-read controls
- Program usage, resource index, Essay Lab, Naseeb Store and team contacts
- Profile-driven College & Aid Finder that uses GPA, SAT, IELTS, major, target countries, budget and portfolio evidence; asks only for missing information and explains each match
- College filters for acceptance, SAT, net price, test-optional, merit, need-based and international aid
- Scholarship catalog with eligibility indicators, funding level, deadline and document requirements
- National and International opportunity-program catalogs with category, delivery and scholarship filters
- Separate task, roadmap and overall journey progress with at-risk deadline indicators for students, counselors and organizations
- Role-specific dashboards, navigation and data isolation
- English-only user-facing interface and demo content
- Django Admin and OpenAPI/Swagger documentation

## Local demo accounts

Run `python manage.py seed_demo` first.

```text
Counselor:    counselor  / admin12345
Organization: schooladmin / school12345
Student:      ramazon    / student12345
```

Demo accounts are development-only. They are enabled by `ENABLE_DEMO_ACCOUNTS=True`, and their local passwords can be replaced with the three `DEMO_*_PASSWORD` variables in `backend/.env`.

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

## Verification

```bash
./scripts/verify.sh
```

The verification runs Django checks, migration-drift detection, backend tests and JavaScript syntax checks.

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
MEDIA_ROOT=/app/backend/media
DOCUMENT_STORAGE_ROOT=/app/backend/private_documents
DOCUMENT_MAX_UPLOAD_SIZE=26214400
```

Start from `backend/.env.production.example` and `frontend/.env.production.example`. Store the real values in the deployment provider's secret manager; do not upload or commit a real `.env` file.

Production startup fails early when `DEBUG=True`, the secret key is missing/weak, `DATABASE_URL` is missing or points to SQLite, or demo accounts are enabled. The `seed_demo` and `reset_demo` commands are also blocked when demo accounts are disabled. Local `.env`, SQLite files, media, virtual environments, build output and dependencies are excluded from Git, Docker build context and release ZIP files.

Production deployment must use PostgreSQL and persistent media storage. Mount `MEDIA_ROOT` and `DOCUMENT_STORAGE_ROOT` on durable volumes and include both locations in backups; production startup rejects missing values. `DOCUMENT_STORAGE_ROOT` is private: never expose it through Nginx, a public `/media/` route, CDN, or object-storage public ACL. Student documents and honor/achievement evidence are streamed only through their authenticated API file endpoints. The included Docker Compose configuration mounts separate `media_data` and `private_document_data` volumes; use equivalent persistent disks on the production server. The included `Procfile`, `build.sh`, `Dockerfile`, healthcheck and Gunicorn configuration support common container or PaaS deployments.

For Render, connect `DATABASE_URL` to one persistent Render PostgreSQL database and keep that same database attached across deploys. Set `APP_ENV=production`, `DEBUG=False`, and `ENABLE_DEMO_ACCOUNTS=False`; Render's hosted-runtime guard refuses to boot with the ephemeral development SQLite fallback. Use `./build.sh` as the build command and the `Procfile` web command (or its equivalent) as the start command. Never use `reset_and_start_backend.sh`, `reset_demo`, or `flush` in a Render build, pre-deploy, or start command. The Render persistent disk stores uploaded files only; it does not replace PostgreSQL. Take a PostgreSQL backup before changing `DATABASE_URL` or deleting/recreating the database service.

Create a clean handoff ZIP without `.env`, SQLite, uploaded media, virtual environments, dependencies or compiled output:

```bash
./scripts/package_release.sh
```

## Project structure

```text
counselor-crm/
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
├── Procfile
└── PROJECT_CHECKLIST.md
```
