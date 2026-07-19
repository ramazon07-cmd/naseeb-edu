# Naseeb Edu — Production Checklist

## Frontend V2 — React/Vite

- [x] Replace the standalone runtime with React 19 + Vite.
- [x] Commit a reproducible `package-lock.json` and verify `npm ci`.
- [x] Connect JWT login, refresh, CRUD, uploads and role-scoped API reads to Django.
- [x] Add a complete student-role cabinet with dedicated Certificates and Meetings pages.
- [x] Add a Student 360° view for counselors and organizations.
- [x] Keep organization access read-only and scoped to its own school's admissions records.
- [x] Remove the palette swatches from authentication while retaining the palette tokens.
- [x] Rebrand the active product to Naseeb Edu with its official purple/silver identity.
- [x] Add persistent light/dark mode with automatic ivory/purple logo switching.
- [x] Use Ivory Paper `#F5F0E6`, Warm Taupe `#B8A58A`, Deep Ink `#4A4036` and Soft Shadow `#D8CEC0` throughout the UI.
- [x] Add responsive counselor, organization and student navigation.
- [x] Add frontend Docker/Nginx build and CI `npm ci` + production build.
- [x] Verify the live frontend origin against Django CORS and JWT endpoints.

## P0 — Security and role isolation

- [x] Audit the current repository and reproduce the critical permission bugs.
- [x] Add the `School` organization model and connect users/students to a school.
- [x] Support the three product roles: Organization School, School Counselor, Student.
- [x] Prevent public registration from creating admin/counselor accounts.
- [x] Prevent students from reading or writing another student's records.
- [x] Restrict Organization School to its own students and their read-only admissions records.
- [x] Add automated permission tests for every role.

## P1 — Role-specific product experience

- [x] Create a dedicated Organization School dashboard.
- [x] Keep the Counselor dashboard as the full control center.
- [x] Create a Student dashboard that only shows the signed-in student's data.
- [x] Show role-specific sidebar items; never render forbidden modules.
- [x] Add school CRUD and school-to-student assignment for counselors.
- [x] Add full student create, edit, delete and detail flows.
- [x] Split My Profile into Academic, Portfolio, Activities and Applications pages.

## P2 — Complete admissions data

- [x] Add Research, Project, Internship, Activity and Honor entities.
- [x] Add recommendation-letter workflow separate from generic documents.
- [x] Add personal statement versions and counselor review history.
- [x] Add university shortlist/deadline filters and status history.
- [x] Add proof uploads, verification and upload-size validation.
- [x] Add notifications for late tasks, missing documents and deadlines.

## P3 — UI and branding

- [x] Remove the old Rustam Bosimov icon/crest from the application UI.
- [x] Replace the current background and landing page with a clean image-free style.
- [x] Improve forms, validation messages, empty states and loading states.
- [x] Make tables, forms and navigation responsive.
- [x] Add accessible keyboard navigation and visible focus states.

## P4 — Production readiness

- [x] Add PostgreSQL production configuration while retaining SQLite for local development.
- [x] Add environment validation and safe production settings.
- [x] Add API throttling, secure headers and upload limits.
- [x] Add backend unit/integration tests and frontend smoke tests.
- [x] Add CI for migrations, tests and frontend checks.
- [x] Add Docker/deployment configuration, health check and verified backup scripts.
- [x] Disable public registration and limit demo-account repair to development.
- [x] Update README with accurate setup, role accounts and deployment instructions.

## Definition of done

- [x] Each role can access only its authorized data and pages.
- [x] Core CRUD workflows work from the frontend through the real API.
- [x] No known critical/high security findings remain.
- [x] Automated tests and CI-equivalent checks pass locally.
- [x] A clean database can migrate, seed and start without manual fixes.
- [ ] Production deployment is verified end-to-end.
