# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Naseeb Edu is a production education-counseling platform (CRM) for Uzbek schools and counselors
managing students who apply to international universities. Accounts are provisioned by staff;
there is no public registration.

---

## 1. Architecture and important directories

Two deployables in one repo. No monorepo tooling, no workspaces.

```
backend/            Django 5.2 + DRF + SimpleJWT + drf-spectacular (Python 3.12)
  core/             settings.py, urls.py, environment.py (runtime guards), wsgi/asgi
  apps/users/       Identity: User(role), TemporaryCredential, audit events, localization
  apps/admissions/  Everything else: ~46 models, all product APIs
frontend/           React 19 + Vite 6 (plain JS/JSX, no TypeScript, no router library)
  src/App.jsx       ~3.3k lines — every page, every component
  src/api.js        The only HTTP client
  src/i18n.js       Translation runtime + Intl formatters
  src/translations/ui.js  uz/ru string tables
  src/styles.css    ~2.1k lines, CSS-variable theme system
scripts/            verify.sh, frontend_smoke.js, i18n_audit.mjs, start/reset/backup helpers
```

Key structural facts:

- **`apps.admissions` is the whole product domain.** `models.py`, `views.py` (~3.1k lines),
  `serializers.py` (~1.9k lines) are large by design. Add to them; do not split them up as a
  side effect of a feature.
- **Business logic lives in modules, not views**: `services.py` (XP awards, Level 1 roadmap),
  `ai_services.py` (RIASEC scoring, college matching, essay review, gateway calls),
  `assistant.py` (streaming chat, PII redaction, prompt-injection refusals),
  `apps/users/credentials.py` (temporary passwords), `apps/users/services.py` (audit, transfers).
- **Frontend is deliberately a small number of large files.** New pages are functions inside
  `App.jsx` registered in `PAGE_META` / `navigationFor()` / `PAGE_RESOURCE_KEYS`. Do not
  introduce a component directory, a router, or a state library without being asked.
- Routing is custom hash routing (`#/page`) over `history.pushState`, driven by `PAGE_META`.
- Frontend runtime dependencies are exactly three: `react`, `react-dom`, `lucide-react`.

### Commands

```bash
./scripts/start_backend.sh      # venv + migrate + runserver 127.0.0.1:8000
```
```bash
./scripts/start_frontend.sh     # npm ci if needed + vite dev on 5173
```
```bash
./scripts/verify.sh             # the full gate: django check, migration drift, tests, npm build, smoke
```

Backend (from `backend/`, with `.venv` activated):

```bash
python manage.py test -v 2
```
```bash
python manage.py test apps.admissions.tests.RoleIsolationTests.test_student_only_lists_own_profile
```
```bash
python manage.py makemigrations --check --dry-run
```

Frontend checks (from repo root):

```bash
node scripts/frontend_smoke.js
```
```bash
node scripts/i18n_audit.mjs --list
```

`npm run check` is an alias for `vite build`; there is no ESLint/Prettier/tsc in this project.

---

## 2. Backend conventions

- Every DRF viewset is scoped through `ScopedQuerysetMixin.filter_for_user()` plus a permission
  class. A new student-owned resource means: model with a `student` FK → serializer →
  `ScopedQuerysetMixin, viewsets.ModelViewSet` with `get_queryset()` returning
  `self.filter_for_user(self.queryset)` → register in `apps/admissions/urls.py`. Anything that
  skips `filter_for_user` is a data-leak bug.
- Permission classes are per-domain and check `view.basename` / `view.action`:
  `CounselorOrOwnerPermission`, `StaffControlledWorkPermission`, `StudentPortalPermission`,
  `MessageChannelPermission`, `SupportTicketPermission`, `ParentLinkPermission`,
  `ProductAdminPermission`. Extend the matching one; do not invent a parallel scheme.
- Role checks use the `User` properties, never string comparison scattered in views:
  `is_product_admin`, `is_counselor_like`, `is_task_manager`, `is_organization`.
- Cross-cutting behaviour goes in mixins: `StaffControlledWorkMixin` (staff-owned tasks/missions),
  `PrivateEvidenceViewSetMixin` (authenticated `proof-file` streaming + file cleanup on delete).
- Custom endpoints use `@action` on the viewset with kebab-case `url_path`
  (`approve`, `mark-viewed`, `extend-level-one`, `transfer-school`).
- Sensitive writes call `audit_product_action(actor=..., action='...', target=...)`. Admin reads of
  Student 360 are audited too — keep that.
- Settings are read with `python-decouple` `config(...)` at module import in `core/settings.py`.
  Never read `os.environ` directly elsewhere.
- Data model style: inherit `TimeStampedModel`, use `TextChoices` inner classes, declare
  `Meta.ordering`, and add named `indexes` / `UniqueConstraint` for anything queried by role scope.

---

## 3. Frontend conventions

- One page = one function in `App.jsx`, plus three registrations: `PAGE_META` (label, icon,
  description), `navigationFor(user)` (which roles see it), `PAGE_RESOURCE_KEYS` (which API
  resources it needs so the bootstrap can partially load and retry).
- Data loading is `Promise.allSettled` per resource, rendered through `PageDataBoundary`. One
  failing endpoint must never blank the whole cabinet — keep skeletons (`PageSkeleton`,
  `ChannelListSkeleton`, `MessageListSkeleton`, `StaffStatsSkeleton`) and `InlineLoadError` retry.
- Simple CRUD forms are declarative: add the resource to `RESOURCE_FIELDS` as
  `[name, label, type, required, choices]` tuples and reuse `ResourceForm` / `DynamicField` /
  `ResourceSection`. Write a bespoke form only when the field tuples genuinely cannot express it.
- Reuse the primitives: `Field`, `CheckboxControl`, `ChoiceCards`, `Modal`, `ActionDialog`,
  `Panel`, `Record`, `Badge`, `Empty`, `PortalTabs`, `ActionMenu`, `StudentWorkspaceSelector`.
- All network access goes through `api` in `api.js`. Never call `fetch` from `App.jsx`. The client
  already handles JWT refresh-on-401, pagination unwrapping (`listAll` follows `next`),
  15s timeouts (120s for uploads/files), `Accept-Language`, and offline detection.
- Every user-visible string goes through `t("…")` or the `tx` tagged template. `LABELS` values are
  passed through `label()` which translates. `window.confirm` messages must be translated too.
- Numbers, dates, percentages, currency and durations use the `formatXLocale` helpers, never
  `toLocaleString` directly.

---

## 4. Database and migration safety

This platform has production data. Treat migrations as irreversible operations.

- Never delete or rename a field/model to "clean up". Add nullable, backfill, then decide later.
- Data backfills use `RunPython` with `apps.get_model(...)` and a `noop` reverse (see
  `admissions/0017_backfill_missing_student_profiles.py`).
- **A migration that backfills data and then adds a constraint/`ALTER TABLE` on the same tables
  must set `atomic = False`.** PostgreSQL defers the FK trigger events from the backfill to commit
  and the DDL then fails. `apps/users/migrations/0004_counselor_requires_school.py` is the
  reference, and `apps/users/test_migrations.py` asserts it stays non-atomic.
- `python manage.py makemigrations --check --dry-run` must be clean; CI fails on drift.
- SQLite is development-only. Migrations must be verified against PostgreSQL behaviour before
  they ship (`docker compose up` gives a local Postgres).
- `School` and `User.school` use `on_delete=PROTECT`. Do not weaken this to `CASCADE`.
- Never run `reset_demo`, `flush`, or `scripts/reset_and_start_backend.sh` against anything but a
  local SQLite database. They are destructive and are explicitly banned from Render build/start
  commands.
- Take a `pg_dump` (`scripts/backup_db.sh`) before any migration touching production.

---

## 5. API conventions

- Everything is under `/api/`. `apps.admissions.urls` is mounted at `/api/` (routers give
  `/api/tasks/`, `/api/students/`, …); `apps.users.urls` at `/api/users/`.
- Auth: `POST /api/auth/token/`, `POST /api/auth/token/refresh/` (rotating + blacklisted).
  Access token 8h, refresh 14 days.
- Pagination is `PageNumberPagination`, page size 25, on every list endpoint. New endpoints
  returning collections must stay paginated — the frontend's `listAll` depends on `next`.
- Throttle scopes are declared in `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`
  (`anon`, `user`, `assistant`, `login`, `password_change`, `credential_issue`) and attached with
  `ScopedRateThrottle`. Any new expensive or credential-adjacent endpoint gets its own scope.
- Errors: raise DRF exceptions and let `ApiErrorLocalizationMiddleware` localize them at the single
  boundary. Do not hand-build localized error payloads in views. The middleware preserves the
  `field`/`code` structure and skips work when the request language is English.
- Enum values exposed to clients must be added to `SPECTACULAR_SETTINGS.ENUM_NAME_OVERRIDES` so
  the OpenAPI schema stays stable. Schema at `/api/schema/`, Swagger at `/api/docs/`.
- Private files are never served as URLs. They stream through authenticated endpoints
  (`/documents/{id}/file/`, `/{resource}/{id}/proof-file/`) with
  `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`.

---

## 6. Authentication and authorization

Six roles on `User.Role`: `admin`, `counselor`, `teacher`, `organization`, `student`, `parent`.

Scope rules currently enforced (`ScopedQuerysetMixin` + permission classes):

| Role | Scope |
| --- | --- |
| `admin` (product admin) | Everything; Student 360 reads are audited |
| `counselor` | Only `assigned_counselor=self` **and** `school=self.school`; a school is mandatory (DB `CheckConstraint`) |
| `teacher` | Students of their own school; controls Tasks/Roadmap missions and approvals |
| `organization` | Own school's students; read-only on admissions records, write only on student provisioning |
| `student` | Only their own records |
| `parent` | Consent-linked children, read-only, and only the sections `ParentStudentLink` permits |

- `is_product_admin` is `is_superuser or role == admin` and is intentionally decoupled from Django
  admin-site access. Do not conflate them.
- `VersionedJWTAuthentication` invalidates tokens whose `pv` claim ≠ `user.password_version`
  (password change revokes all sessions) and blocks every path except `/users/accounts/me/` and
  `/users/accounts/change-password/` while `must_change_password` is set.
- Staff provision students; students receive a one-time `TemporaryCredential` (TTL from
  `TEMPORARY_CREDENTIAL_TTL_HOURS`, default 72h) and are forced through `ForcedPasswordChange`.
  Every credential event is written to `CredentialAuditEvent`.
- Public registration is disabled. Do not re-enable `RegisterView` for privileged roles.
- Some data is hidden from staff by policy, not just by UI: private messages, moderation reports,
  internal counselor notes, meeting notes, essay drafts/feedback, task submission content, roadmap
  reflections, screen-time detail and support tickets are excluded from the school/admin
  Student 360 (`SchoolVisibility*` serializers). Changing what those serializers expose is a
  privacy decision, not a refactor.

---

## 7. Question systems (and what "English" means here)

**There is no English-language exam, test or question-bank module in this repository.** Two
question systems exist, both small and both driven from the backend:

1. **RIASEC personality assessment** — `ai_services.RIASEC_QUESTIONS`: 12 tuples of
   `(id, trait, en_text, uz_text, ru_text)`, answered 1–5. Scored by
   `score_personality_answers()` into six trait percentages plus two top traits; stored once per
   student on `PersonalityAssessment` (`framework='riasec-v1'`). Served/submitted at
   `/api/personality-assessment/`; the submission serializer rejects any payload whose answer keys
   are not exactly the question set. It is an education-interest snapshot, not a diagnosis — keep
   that framing in copy. It is private to the student and feeds university matching via
   `personality_university_fit()`.
2. **College research profile questions** — `COLLEGE_RESEARCH_QUESTIONS` in `views.py`, surfaced by
   `build_college_research()` as `missing_fields` + `questions` so the UI (`CollegeProfileQuestions`)
   only asks for profile data the student has not filled in yet.

**English is the source language of the product**, and that is the sense in which English is the
current functional priority:

- Translation keys *are* the English strings. `TRANSLATIONS.en` is intentionally `{}` — `t()`
  falls back to the key. Never translate the key itself.
- New UI copy is written in English inside `t("…")`, then given uz/ru entries in
  `src/translations/ui.js` (or the inline tables in `i18n.js`).
- `node scripts/i18n_audit.mjs` must report `missing uz/ru keys: 0` and
  `untranslated dynamic messages: 0` (currently 1186 keys, 0/0).
- Backend messages follow the same rule: English is the literal in code, uz/ru live in
  `apps/users/localization.py`, and the middleware returns early for English.
- `frontend_smoke.js` fails the build if certain Uzbek fragments reappear as hardcoded copy in
  `App.jsx`.

When adding a new question set, follow the RIASEC pattern: questions defined once in the backend
with all three languages, validated server-side against the canonical id set, scored in
`ai_services.py`, rendered by a generic form component.

---

## 8. Math and IQ — placeholder status

Not implemented. There is no Math module, no IQ module, no score fields, no endpoints, no UI, and
no migrations for either. Do not describe them as existing, and do not scaffold empty models,
routes or navigation entries for them unless explicitly asked.

The only related placeholder that exists today is the dashboard discovery card gated on
`VITE_PERSONALITY_QUIZ_URL`: when the variable is empty it renders a disabled
`"Link coming soon"` button. That is the established pattern for an unbuilt assessment — an
env-gated, visibly disabled entry point — and is the pattern to copy if Math or IQ needs a
placeholder before it is real.

If Math or IQ is built later, it should reuse the section 7 pattern (backend question bank,
server-side scoring, one model per student, private-to-student by default) rather than a new
subsystem.

---

## 9. Testing requirements

- Django's test runner only. There is no pytest, no factory library, no frontend test runner.
- Tests live next to the app: `apps/admissions/tests.py` (89 tests), `test_visibility.py`,
  `test_evidence_files.py`, `apps/users/tests.py`, `test_admin_control.py`, `test_migrations.py`,
  `core/tests.py`.
- **Every permission or scope change needs a regression test proving the negative case** — that the
  wrong role gets 403/404 and cannot see the record. This is the convention the whole suite is
  built on; follow it.
- `scripts/frontend_smoke.js` is a hard structural contract over `App.jsx`, `api.js`, `index.html`
  and `styles.css`. It asserts function names, exact copy strings, API method names, CSS tokens and
  brand assets. Renaming `function StudentOverview(` or changing a checked string breaks CI. Read
  the relevant assertion before renaming anything, and update the assertion in the same commit when
  the change is intended.
- `scripts/frontend_smoke.js` currently passes. It previously failed on
  `First-paint and authenticated bootstrap loading states are missing.` because a landing-page
  rewrite had replaced the `class="app-boot"` boot markup in `frontend/index.html`; the markup was
  restored, so both that assertion and the hardcoded-colour assertion it was masking now pass.
- CI (`.github/workflows/ci.yml`) runs migration drift check, backend tests, `npm ci`,
  `npm run build`, then the smoke script. `./scripts/verify.sh` reproduces it locally.

---

## 10. Security requirements

- `core/environment.py` refuses to boot production when `DEBUG=True`, `SECRET_KEY` is weak/known,
  `DATABASE_URL` is missing or SQLite, demo accounts are enabled, or `MEDIA_ROOT` /
  `DOCUMENT_STORAGE_ROOT` are unset. Hosted runtimes (`RENDER=1`) are forced to production. Do not
  loosen these guards to make a deploy succeed.
- `DOCUMENT_STORAGE_ROOT` is private storage. `PrivateDocumentStorage.base_url` returns `None` on
  purpose. Never expose it through Nginx, `/media/`, a CDN or a public bucket ACL, and never switch
  a private `FileField` to the default storage.
- Uploads are validated on extension (`DOCUMENT_ALLOWED_EXTENSIONS`) and size
  (`DOCUMENT_MAX_UPLOAD_SIZE`, 25 MB) and stored under UUID filenames.
- AI provider credentials are backend-only. `AI_GATEWAY_API_KEY` must never be mirrored into a
  `VITE_*` variable — anything `VITE_*` is public in the bundle.
- The assistant is read-only by design: no tools, no writes. It redacts PII (`redact_pii`), refuses
  prompt-injection/credential/cross-student requests (`BLOCKED_REQUEST_PATTERNS`), audits metadata
  only, and keeps history only for the open page session. Adding a write-capable tool requires
  explicit confirmation, audit and idempotency — it is tracked as unfinished work in `todo.todo`.
- Demo accounts and demo passwords exist only when `ENABLE_DEMO_ACCOUNTS=True`; `seed_demo` exits
  without writing when disabled. Never hardcode a demo credential into product code.
- Do not commit `.env`, SQLite files, uploaded media, or `private_documents/` (all gitignored).

---

## 11. Performance requirements

- Role-scoped querysets fan out across relations — always pair them with `select_related`
  (`'student__user'`, `'student__assigned_counselor'`, `'student__school'`) and `prefetch_related`
  the way the existing viewsets do. An N+1 in a list endpoint is amplified by `listAll` walking
  every page.
- Keep list endpoints paginated; `listAll` aborts after 100 pages.
- The frontend loads only the resources named in `PAGE_RESOURCE_KEYS` for the active page. Adding a
  resource to a page's list has a real cost — add it only if that page renders it.
- Vite manual chunks split `translations`, `icons` and `react-vendor`. Import icons individually
  from `lucide-react`; never `import * as icons`.
- No render-blocking remote resources: no Google Fonts, no `@import url(...)` in CSS, no CDN
  scripts. The smoke test enforces this. Brand logos are preloaded in `index.html` and swapped via
  CSS tokens so theme changes cause no flash or refetch.
- Screen-time tracking batches to at most 50 entries every 30s, counts only visible-tab active
  seconds, and queues offline — do not make it chattier.

---

## 12. UI/UX and design principles

- **Colors only via CSS variables.** `styles.css` defines the full token set on `:root` and
  overrides it on `:root[data-theme='dark']`. The smoke test rejects any hex or `rgba()` appearing
  in the component-section of the stylesheet and any `var(--token)` that is never defined.
- Light theme is the Naseeb ivory/taupe system (`#F5F0E6`, `#B8A58A`, `#4A4036`, `#D8CEC0`);
  dark theme is the purple/silver identity (`#4A1368`, `#C0C0C6`, `#1A1A1F`, `#F2F2F5`).
  Dark mode must not reuse light accents — there are explicit smoke assertions against that.
- Theme is applied pre-paint by an inline script in `index.html` (localStorage → OS preference),
  persisted under `naseeb-edu-theme`, and mirrored by `useLayoutEffect`. Both the theme toggle and
  the language selector are available on the landing page, login and every authenticated page.
- Every list needs loading, empty (`Empty`), and error states. Every mutation needs a busy state
  (`aria-busy`) and a `notify` result message.
- Accessibility is part of the contract already in place: `aria-label` on icon-only buttons,
  `aria-pressed` on toggles, combobox semantics on global search, visible focus rings,
  `prefers-reduced-motion` handling. Keep it.
- Responsive down to 320px; long user content (student names, target countries) must wrap —
  `overflow-wrap: anywhere` and `min-width: 0` guards exist for this and are smoke-tested.
- Student-facing screens render inside the `student-portal` scope so they inherit the student
  theme; keep new student UI inside it.

---

## 13. Git safety

- Work on a branch. `main` is the deploy branch.
- Never `git reset --hard`, force-push, rewrite history, or delete branches.
- The working tree usually carries in-progress feature work (currently: landing page, personality
  assessment, migration `0025`, `frontend/public/landing/`). Run `git status` and stage only the
  files belonging to your change — never `git add -A` blindly.
- `frontend/dist/` is gitignored build output; if it appears locally, leave it out of commits.
- Commit style is conventional and scoped: `feat(admissions):`, `fix(migrations):`,
  `fix(production):`, `docs:`, `test(project):`.
- Do not commit `.env`, database dumps, or files under `private_documents/`.

---

## 14. Development workflow

1. Read the relevant code first — models, the viewset's permission class, the serializer, and the
   `App.jsx` page. This codebase has strong existing conventions and few obvious file boundaries.
2. `todo.todo` (Uzbek) is the live product/engineering backlog with EASY/MEDIUM/HARD items, a
   delivery order, and open blocking product questions. `PROJECT_CHECKLIST.md` is the completed
   production checklist. Check both before assuming something is unbuilt or unowned.
3. Implement backend first (model → migration → serializer → viewset/permission → URL), then the
   API client method, then the page in `App.jsx`, then uz/ru translations.
4. Run `python manage.py test` for the touched app, then `node scripts/i18n_audit.mjs`, then
   `node scripts/frontend_smoke.js`, then `./scripts/verify.sh` before declaring done.
5. Local URLs: app `http://127.0.0.1:5173/`, API docs `http://127.0.0.1:8000/api/docs/`,
   health `http://127.0.0.1:8000/api/health/`, Django admin `http://127.0.0.1:8000/admin/`.
6. Demo logins (development only, `ENABLE_DEMO_ACCOUNTS=True`, after `python manage.py seed_demo`):
   `counselor/admin12345`, `schooladmin/school12345`, `ramazon/student12345`.

---

## 15. Modifying existing functionality

- Existing behaviour is load-bearing. Before changing anything, find its callers, its permission
  class, its test, and its `frontend_smoke.js` assertion.
- Things that are the way they are on purpose — change only with an explicit request:
  - Notification UI is **removed** from the frontend; the backend model/API is kept pending a
    product decision. The smoke test fails if notification UI returns.
  - Roadmap progress is not manually editable; students submit, staff approve.
  - Self-assigned tasks (`is_self_assigned`) never award XP.
  - XP is awarded once per approval through an `XPTransaction` ledger; level-ups are staff-approved
    (`LevelApproval`), never automatic.
  - Level 1 roadmap extension is idempotent (`extend_level_one_roadmap` uses `get_or_create` and
    never resets existing work).
  - `MeetingNote` and `Booking` are distinct; the "Meetings" page is Bookings.
  - Organization access to admissions records is read-only.
- Keep diffs focused. Do not reformat `App.jsx`, `views.py` or `styles.css`, and do not "modernize"
  surrounding code while implementing a feature — large-file diffs are already hard to review.
- The README describes the UI as English-only; that is stale — the product is trilingual (uz/ru/en)
  with Uzbek as the default `LANGUAGE_CODE`. Prefer the code over the README when they disagree,
  and fix the README when you touch that area.

---

## 16. Frontend design workflow

Naseeb Edu is a serious education product used by students, parents, teachers, counselors, school
organizations and admins. The UI must read as **trustworthy, clear, intelligent and professional**,
and student-facing screens must additionally feel welcoming. Do not apply one generic pattern to
every role — a counselor triaging 40 students needs density and scanning; a student needs focus and
one obvious next action; a parent needs reassurance and read-only clarity.

### Required order of work

Never jump straight to code. Every frontend task runs in this order:

1. **UX reasoning** — who is the user, what task, what is the one primary action on this screen.
2. **Design direction** — the intent before the pixels.
3. **Existing design-system inspection** — read `styles.css` tokens and the `App.jsx` primitives
   *first* (see section 3 and the checklist below). Extend what exists.
4. **Component architecture** — reuse `Field`/`Modal`/`Panel`/`Record`/`PortalTabs`/`Empty` before
   writing anything new.
5. **Implementation.**
6. **Responsive verification** — 320px, 560px, 820px, 1100px, desktop.
7. **Accessibility verification** — contrast, focus order, `aria-*`, keyboard paths.
8. **Visual polish.**
9. **Final design audit.**

### Design skills available

Three design plugins are installed at user scope and auto-discover in this repo:

- **`frontend-design`** (`frontend-design:frontend-design`) — aesthetic direction and typography
  for new UI. Use at step 2.
- **`impeccable`** (`/impeccable <command> <target>`, 23 commands) — use `critique` and `audit` at
  step 9, `extract` at step 3 to pull the existing system, `polish`/`layout`/`typeset`/`harden` for
  targeted passes. It also installs PostToolUse/Stop hooks that check UI edits automatically.
- **`ui-ux-pro-max`** — searchable style/palette/font-pairing/chart databases and per-stack
  guidance. Use for reference, **not** as a source of a new palette: Naseeb Edu's palette is
  already fixed (section 12).

### Anti-patterns — do not ship these

Generic SaaS dashboard templates · card-inside-card layouts · a card around every element ·
random gradients · purple/blue "AI product" aesthetics · Inter/system-font-only styling ·
arbitrary one-off shadows · ever-larger rounded corners · decoration with no function ·
inconsistent spacing · flat hierarchy where everything has equal weight · animation for its own sake.

### Non-negotiables

Strong visual hierarchy · clear information architecture · consistent typography · intentional
spacing · accessible contrast in **both** themes · responsive layouts · design tokens over literals
· purposeful motion that respects `prefers-reduced-motion` · explicit empty / loading / error states
on every surface · a visual identity specific to Naseeb Edu.

### Design-system discovery checklist

Before changing any page, inspect and write down what already exists:

colors (290 `--*` tokens in `styles.css`) · typography (`Cinzel` display + `Montserrat` body —
see the known gap in section 9) · spacing · the `App.jsx` primitives · `lucide-react` icons ·
`.button` variants (`primary`, `light`, `quiet`, `small`) · `Field`/`CheckboxControl`/`ChoiceCards`
· `navigationFor()` + `PAGE_META` · `StudentTable` · `Modal`/`ActionDialog` · the `*-card` families
· `Empty` · the skeleton components · `InlineLoadError` · the six breakpoints.

**If the system already covers it, extend it. If the system is inconsistent, name the
inconsistency in your plan before changing it** — do not silently introduce a competing scale.
Known inconsistencies to work against rather than add to: ~15 distinct `border-radius` values, no
spacing scale (4–24px ad hoc, including 7/9/11/13px), ~50 hand-rolled `box-shadow` geometries
against 37 tokenised ones, and six unrelated breakpoints.

Before redesigning an existing page, read its current implementation and keep the patterns that
work. Blanket replacement is not a redesign.

---

## 17. Specialist agent delegation

Eight project-scoped agents live in `.claude/agents/`. They are tools for the main agent, not a
mandatory pipeline — **the main agent is the orchestrator and owns every delegation decision.**
Subagents cannot spawn subagents; a multi-step workflow returns to the main agent between steps.

| Agent | Writes | Use for |
| --- | --- | --- |
| `naseeb-orchestrator` | no | Scoping large or ambiguous work — returns a delegation plan only |
| `naseeb-uiux` | no | Design specs, IA, hierarchy, responsive and motion strategy, design critique |
| `naseeb-frontend` | **yes** | `App.jsx` / `styles.css` / `api.js` / translations implementation |
| `naseeb-backend` | **yes** | Models, serializers, viewsets, permissions, migrations, services |
| `naseeb-qa` | no | Running the real gate + browser verification across viewports/themes/languages |
| `naseeb-code-reviewer` | no | Diff review ranked CRITICAL/HIGH/MEDIUM/LOW |
| `naseeb-performance` | no | Measured bundle, media, render and query-cost analysis |
| `naseeb-impeccable` | no | Final visual quality gate before shipping frontend work |

### When not to delegate

Do the work directly for: single-file edits, copy and typo fixes, one translation key, answering a
question from the code, renaming a local variable, or anything where writing the brief costs more
than doing the work. **Spawning an agent for a trivial task is a failure mode, not thoroughness.**
Each spawn starts cold and re-derives context the main agent already has.

### Routing

- Visual → `naseeb-uiux` → `naseeb-frontend` → `naseeb-impeccable`
- Backend → `naseeb-backend` → `naseeb-qa` → `naseeb-code-reviewer`
- Full-stack → `naseeb-uiux` + `naseeb-backend` → `naseeb-frontend` → `naseeb-qa` →
  `naseeb-code-reviewer` → `naseeb-performance`
- Bug → relevant specialist → `naseeb-qa` → `naseeb-code-reviewer` if it touches shared code
- Performance → `naseeb-performance` → implementer → `naseeb-qa`
- Design critique only → `naseeb-uiux` → `naseeb-impeccable`

Adapt to the task. Do not run every agent on every request.

### Single-writer rule

`App.jsx`, `views.py`, `serializers.py` and `styles.css` are single-writer files. Never run two
writing agents against the same file concurrently — sequence them through the main agent instead.
Agents touching disjoint files may run in parallel.

### Reporting

A subagent's final report is not shown to the user. The main agent must relay what matters,
including failures. Never present an agent's unverified claim as a verified result.
