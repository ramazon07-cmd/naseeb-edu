# Naseeb Edu

**A shared workspace for schools, counselors, students and families managing international university applications.**

Naseeb Edu connects student profiles, university research, tasks, essays, documents and counselor feedback in one application journey. Schools oversee their students, counselors guide the students assigned to them, and students work through the next steps in their own private workspace.

The repository contains a React frontend and a Django REST API. Local development supports SQLite; production deployments should use PostgreSQL and persistent file storage.

## Contents

- [Product overview](#product-overview)
- [Access and privacy](#access-and-privacy)
- [Technology and structure](#technology-and-structure)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Student import](#student-import)
- [Verification](#verification)
- [Docker](#docker)
- [Production deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Development guidelines](#development-guidelines)

## Product overview

| Workspace | What it supports |
| --- | --- |
| Student dashboard | A next-task focus, deadline-based priorities, work awaiting review, upcoming meetings, journey progress and XP |
| Student Center | Academic results, target countries and majors, budget, projects, internships, activities, honors and supporting records |
| Roadmap and tasks | Assigned missions, student responses and reflections, staff review, completion tracking and approval-backed progression |
| University research | University and scholarship filters, profile-based matching, explanations, funding requirements and shortlists |
| Applications | University choices, application stages, deadlines, scholarship information and decisions |
| Essays and documents | Drafts, revision records, counselor feedback, file uploads, review states and Google Docs links |
| Counselor and school tools | Student management, spreadsheet import, scoped Student 360 views, assignments and progress monitoring |
| Communication | Direct and group messages, school communities, discussions, meetings, reports and moderation |
| Administration | School and counselor provisioning, account management, counselor roadmaps and audit records |
| Additional tools | Personality and interests assessments, opportunity programs, resources, program usage, service catalog and an AI assistant |

The interface includes Uzbek, Russian and English translations, responsive layouts, and light and dark themes. User-authored content retains its original language; translation coverage should be checked when adding or changing screens.

University match scores describe profile and preference fit. They are not admission probabilities or scholarship guarantees. The assessment catalog includes both available and planned challenges; planned entries should not be presented as completed assessments.

## Access and privacy

### Public website versus private workspace

The landing page presents the product, team, student stories and illustrative workspace previews. It does **not** receive the authenticated dashboard's student records. Private profiles, tasks, applications, essays, documents and messages require an authenticated API request and the appropriate role scope.

There is no public self-service sign-up. Accounts are provisioned through authorized administration, counselor or school workflows. The legacy `/api/users/register/` endpoint is restricted to product administrators; signing in as a student does not grant permission to create another account.

Issued temporary credentials have a configurable lifetime, and accounts marked for a password change must complete that step before using the workspace. Logging out clears the frontend's private workspace state. The API remains the source of truth for authorization; hiding a menu item is not an access-control mechanism.

### Roles

| Role | Intended scope |
| --- | --- |
| Product administrator | Platform administration, school and counselor provisioning, permitted student oversight and audit records |
| Counselor | Assigned students and their admissions work, with school/workspace restrictions enforced by the API |
| Teacher | Permitted students in their school, tasks, roadmap missions, submissions and approvals |
| School organization | Its own students, student management and scoped Student 360 oversight |
| Student | Their own profile, tasks, submissions, applications, documents and student tools |
| Parent | Linked children and the progress sections allowed by the parent-access policy |

This table summarizes access. Individual actions, files and communication channels have additional permission checks.

### Files and public aggregates

- Private student documents and honor/achievement evidence are delivered through authenticated file endpoints. Never publish `DOCUMENT_STORAGE_ROOT` as a static directory.
- `/api/public/reach/` is an intentionally unauthenticated, count-only regional aggregate. It returns coverage counts rather than student profiles. `PUBLIC_REACH_MIN_CELL` controls suppression of small regional counts; its default is `0`.
- Google Docs previews depend on the external document's sharing settings. A validated link does not grant access to the document or change its permissions.
- Secrets belong on the backend. Every `VITE_*` value is public frontend configuration and may be included in the browser bundle.

## Technology and structure

| Layer | Implementation |
| --- | --- |
| Frontend | React 19, Vite 6, JavaScript/JSX, CSS, Lucide icons and Three.js |
| API | Python, Django 5.2, Django REST Framework and Simple JWT |
| API documentation | OpenAPI schema, Swagger UI and ReDoc through drf-spectacular |
| Database | SQLite for development; PostgreSQL for production |
| Spreadsheet parsing | openpyxl for `.xlsx`, xlrd for `.xls`, and CSV parsing |
| Serving | Gunicorn for the API; Nginx in the frontend container |
| Automation | GitHub Actions, Django tests, frontend build and smoke checks |

```text
Naseeb-Edu-Production/
├── backend/
│   ├── apps/users/           # Accounts, credentials, authentication and access
│   ├── apps/admissions/      # Student records and admissions workflows
│   ├── core/                # Settings, URLs and runtime configuration guards
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── public/              # Brand assets, fonts and public landing content
│   ├── src/                 # Public pages, private workspace, API client and translations
│   ├── tests/               # Focused JavaScript tests
│   ├── package.json
│   └── package-lock.json
├── scripts/                 # Local startup, verification and release packaging
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile
├── build.sh
└── Procfile
```

## Local development

### Prerequisites

Use **Python 3.12** and **Node.js 22**, matching the repository's CI configuration. You also need npm and Git. PostgreSQL is optional for local development; Docker Compose is an alternative to the manual setup below.

Run commands from the repository root unless a working directory is shown. The examples use Bash or Zsh. Copy each environment template only when the destination `.env` does not already exist.

### 1. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

An empty `DATABASE_URL` selects the local SQLite database. To use PostgreSQL, set `DATABASE_URL` before running migrations.

### 2. Start the frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

The frontend defaults to `http://127.0.0.1:8000/api`. Use `npm ci` to install the dependency versions recorded in the lockfile.

| Service | Local URL |
| --- | --- |
| Website and workspace | [127.0.0.1:5173](http://127.0.0.1:5173/) |
| Sign in | [127.0.0.1:5173/#/login](http://127.0.0.1:5173/#/login) |
| Swagger UI | [API documentation](http://127.0.0.1:8000/api/docs/) |
| ReDoc | [API reference](http://127.0.0.1:8000/api/redoc/) |
| OpenAPI schema | [Schema endpoint](http://127.0.0.1:8000/api/schema/) |
| Health endpoint | [API health](http://127.0.0.1:8000/api/health/) |
| Django administration | [Django Admin](http://127.0.0.1:8000/admin/) |

The health endpoint reports that the application can respond; it is not a database or storage readiness check.

### 3. Choose demo data or administrator access

For a **local demo database**, activate the backend virtual environment and run:

```bash
cd backend
source .venv/bin/activate
python manage.py seed_demo
```

Seeding requires `ENABLE_DEMO_ACCOUNTS=True`, as set in the development template. It writes sample records and sets demo credentials, so use it only against a development database.

| Demo role | Username | Default development password |
| --- | --- | --- |
| Counselor | `counselor` | `admin12345` |
| School organization | `schooladmin` | `school12345` |
| Student | `ramazon` | `student12345` |
| Parent | `parent` | `parent12345` |

Override these passwords with the corresponding `DEMO_*_PASSWORD` settings. They are development examples, not production credentials. `VITE_SHOW_DEMO_ACCOUNTS` controls the development login hint; it does not create accounts.

For a clean database, create an administrator instead:

```bash
cd backend
source .venv/bin/activate
python manage.py createsuperuser
```

### Startup shortcuts

The repository also provides two-terminal startup scripts:

```bash
# Terminal 1
./scripts/start_backend.sh
```

```bash
# Terminal 2
./scripts/start_frontend.sh
```

The backend script prepares its virtual environment, installs requirements, creates a missing `.env`, applies migrations and starts the API. The frontend script installs dependencies when `node_modules` is absent and starts Vite. Neither script seeds demo data automatically.

## Configuration

Use `backend/.env.example` and `frontend/.env.example` for local settings, and the corresponding `.env.production.example` files as deployment templates. Real `.env` files and credentials must remain outside version control.

| Setting | Purpose |
| --- | --- |
| `APP_ENV` | Runtime mode: `development`, `test` or `production` |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Django security and host configuration |
| `DATABASE_URL` | Database connection; empty selects SQLite in development |
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API, including scheme and port |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins for CSRF-protected requests |
| `ENABLE_DEMO_ACCOUNTS` | Enables development demo workflows; must be false in production |
| `MEDIA_ROOT` | Persistent location for application media |
| `DOCUMENT_STORAGE_ROOT` | Separate private document storage location |
| `DOCUMENT_MAX_UPLOAD_SIZE` | Document upload limit in bytes; template default is 26,214,400 |
| `TEMPORARY_CREDENTIAL_TTL_HOURS` | Temporary credential lifetime; template default is 72 hours |
| `STUDENT_IMPORT_RATE` | Student-import throttle; template default is `30/hour` |
| `PUBLIC_REACH_MIN_CELL` | Small-cell suppression threshold for public regional counts |
| `VITE_API_URL` | Browser-facing API base URL, including `/api` |
| `VITE_SHOW_DEMO_ACCOUNTS` | Development-only login hint; normally `false` |

The frontend templates also contain meeting, contact and social-link configuration. Restart Vite after changing its environment. Production frontend values are applied at **build time**, so changing them requires a new build.

The AI assistant is optional. Its backend settings include `AI_ASSISTANT_ENABLED`, `AI_GATEWAY_API_KEY`, model names, rate limits and request limits. Without a provider key, the application uses its built-in guidance fallback. Never put provider keys into a `VITE_*` variable.

## Student import

Authorized administrators, counselors and school organizations can use **Students → Import students**.

1. Select an `.xlsx`, `.xls` or UTF-8 `.csv` file.
2. Map the full-name and grade columns, then any optional profile fields.
3. Review the dry-run preview, validation errors and duplicate rows.
4. Confirm the import of ready rows.
5. Download the generated temporary credentials before closing the result window.

A preview does not create accounts. The source spreadsheet is parsed in memory rather than retained as an uploaded source file. Import limits are **5 MB**, **2,000 data rows** and **100 columns**; compressed workbooks also have expansion limits.

Optional fields include contacts, academic scores, target major and countries, budget, scholarship needs and a Google Docs portfolio link. Unmapped payment, contract, address, workplace and JSHSHIR columns are not included in the preview response or student profile. Account creation remains subject to the caller's permissions and school scope.

Treat the one-time credential export as sensitive account information. For repeated imports, inspect the preview and duplicate results before confirming.

## Verification

After installing dependencies, activate the backend environment and run the repository checks from the root:

```bash
source backend/.venv/bin/activate
./scripts/verify.sh
```

The script runs Django system checks, migration-drift detection, backend tests, `npm ci`, the production frontend build and frontend smoke checks.

Run the focused JavaScript tests separately:

```bash
node --test frontend/tests/*.test.mjs
```

To check the private-portal access boundary specifically:

```bash
cd backend
source .venv/bin/activate
python manage.py test apps.users.test_portal_access
```

GitHub Actions runs migration checks, backend tests, the frontend build and frontend smoke checks on pushes and pull requests. The standalone JavaScript test command above is not currently included in that workflow.

For interface changes, also verify the relevant role in a browser: successful actions, empty/loading/error states, mobile widths, supported languages and both themes. For authentication changes, verify that logout removes private content and that anonymous API requests remain rejected. Passing a build alone does not establish those behaviors.

## Docker

From the repository root:

```bash
docker compose up --build
```

This starts PostgreSQL 16, Django/Gunicorn and the Nginx-served frontend. Open [the frontend on port 3000](http://127.0.0.1:3000/); the API remains on port 8000.

The supplied Compose file is configured for **local development**, with example credentials and demo workflows enabled. It applies migrations but does not seed sample data automatically. To populate the local Compose database:

```bash
docker compose exec backend python manage.py seed_demo
```

Database, media and private documents use separate named volumes. `docker compose down` stops the environment; adding `-v` also removes its persistent volumes and data.

## Production deployment

Prepare deployment-specific values from `backend/.env.production.example` and `frontend/.env.production.example`.

Before serving traffic:

1. Set `APP_ENV=production`, `DEBUG=False` and `ENABLE_DEMO_ACCOUNTS=False`.
2. Supply a unique `SECRET_KEY` of at least 32 characters and a persistent PostgreSQL `DATABASE_URL`.
3. Set the actual API hosts, frontend CORS origins and trusted CSRF origins.
4. Configure persistent `MEDIA_ROOT` and `DOCUMENT_STORAGE_ROOT` locations. Back up the database and both storage locations.
5. Keep private document storage behind authenticated API endpoints; do not mount it under a public web-server path or public storage ACL.
6. Install dependencies, collect static files, apply migrations and build the frontend with the production `VITE_API_URL`.
7. Serve the API through Gunicorn and configure HTTPS and the deployment's reverse proxy.
8. Verify sign-in, role isolation, file access and a representative workflow against the deployed environment.

Runtime configuration guards reject production startup with debug mode, an insecure secret, missing database configuration, SQLite, enabled demo accounts or missing storage paths. These guards do not replace deployment and backup verification.

The repository provides:

- `Dockerfile`: API image, static-file collection, migrations and Gunicorn startup.
- `build.sh`: backend dependency installation, static-file collection and migrations.
- `Procfile`: migrations followed by Gunicorn, using `PORT` or port 8000.
- `frontend/Dockerfile`: frontend build and Nginx serving.

The backend build script does not build or deploy the frontend. Plan its deployment separately, or use the frontend container. Since the supplied build/start commands apply migrations, coordinate that step with database backups and your release process.

On Render, the repository's hosted-runtime guard requires production mode and prevents a silent fallback to development SQLite. Keep the persistent PostgreSQL database attached across deployments; a file-storage disk does not replace it. Do not run `reset_demo`, `flush` or reset/start demo scripts against production data.

### Source handoff

```bash
./scripts/package_release.sh
```

The script creates a source ZIP and filters common environment files, development databases, dependencies and generated output. Review its exclusions before packaging: custom storage paths and `private_documents` directories require particular attention. Inspect the archive before sharing it; do not treat packaging as a substitute for checking that student files and secrets are absent.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Login reports a connection error | API process, `VITE_API_URL` and the exact frontend origin in `CORS_ALLOWED_ORIGINS` |
| Demo login fails | Run `seed_demo` against the intended development database; check demo enablement and password overrides |
| Workspace opens a required password-change screen | Complete the issued-account password-change flow |
| A user cannot see a student | Check school membership, counselor assignment, parent linkage and the endpoint's permission scope |
| Google Docs preview is unavailable | Check the external document URL and its sharing permissions |
| Port 5173 is occupied | Stop the conflicting process or choose another Vite port and allow that origin in backend CORS settings |
| Production refuses to start | Read the configuration error and compare the deployment settings with the production template |
| Changes to frontend environment settings do not appear | Restart the development server or rebuild the deployed frontend |

## Development guidelines

- Keep public landing content independent of authenticated student data.
- Enforce new access rules in the API and add role-isolation coverage when permissions change.
- Add new interface copy to the Uzbek/Russian translation dictionary and check English fallback behavior.
- Keep new database changes in migrations and validate migration drift before a release.
- Preserve `package-lock.json`; update it deliberately when dependencies change.
- Use a separate demo or test database for experiments, imports and destructive maintenance.
- Report the checks actually run in a change description, together with any unverified behavior.
