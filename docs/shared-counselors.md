# Shared counselors and adding counselors: study

Status: study. Nothing in this document is built yet. Related: `docs/product-vision-and-stages.md` (D4 pricing unit,
D6 counselor model, S2.1 plans).

## Decision (2026-10-06), tracked in issue #52

- A Naseeb admin opens access for a school (the workspace and its organization account).
- **Only a Naseeb admin adds counselors.** The school does not add counselors, so option C below is replaced.
- The school's organization account can **edit** the counselors of its own school.
- Counselor seats in a school workspace are **unlimited for now**. When payments are added, the paid plan sets the
  number of seats again.
- Shared counselors (option A) and one counselor in several workspaces (option B) are not decided yet.

## 1. How it works today (verified in the code)

- **A counselor belongs to exactly one workspace.** `User.school` is required for counselors (DB constraint
  `counselor_requires_school`).
- **A student has at most one counselor.** `StudentProfile.assigned_counselor` is one foreign key, and the
  counselor must be in the student's school (`serializers/students.py`, `views/students.py` `assign-counselor`).
- **A counselor sees only their own students.** `scoping.student_lookups()` returns
  `assigned_counselor = me AND school = my school`. Lists, Student 360, files, essays and search all go through it.
- **Only a product admin adds counselors.** The admin uses `create-counselor`, `create-individual-counselor` and
  `transfer-school` in `apps/users/views.py`. A school's organization account cannot add counselors.
- **Seats come from the plan** (`users/entitlements.py`): School Standard has 3 counselors, Individual has 1 and
  Center has no limit. `entitlements.check()` locks the school row, so two parallel creations cannot both take the
  last seat.
- **Assigning:** a counselor can take unassigned students of their own school. An admin can assign or reassign
  any student.
- **Features that use "the" counselor** (the single assigned one):
  - essay sharing and its notice (`essay_lab/access.py`, `essay_lab/views.py`)
  - parent invites (`views/parents.py`)
  - student → counselor messages (`views/portal.py`)
  - challenge results (`views/challenges.py`)
  - messaging contacts (`views/messaging.py`)
  - progress summaries, cached per scope key (`progress_cache.py`, `scoping.student_scope_key`)

## 2. What "shared counselor" can mean

| | Meaning | Example |
| --- | --- | --- |
| A | One student, several counselors | The school counselor plus a Naseeb expert; a lead counselor plus an assistant |
| B | One counselor, several workspaces | A Naseeb or freelance counselor who serves two or three schools |
| C | The school adds its own counselors | The organization account opens counselor accounts within its plan's seats |

## 3. Options

### A. Co-counselors for a student (shared counselor)

- **Model:** a new `StudentCounselor` table (`student`, `counselor`, `added_by`, `created_at`), unique on
  (`student`, `counselor`).
  - `assigned_counselor` stays as the **lead counselor**. Nothing is renamed, deleted or backfilled.
- **Scope:** the counselor rule becomes `assigned_counselor = me OR shared with me`, still inside the counselor's
  own school.
  - It is one function, but `student_lookups()` returns a dict of lookups today, and this needs a `Q`.
  - That change touches `scope_students()`, `student_scope_key()` (progress cache keys) and the assignment queries.
- **Per-feature choices:** every place in the "the counselor" list above needs a rule: lead only, or every
  counselor of the student. For example: who gets the essay-shared notice, who can invite parents, and who receives
  student messages.
- **Effort:** M (3–5 days), including a negative test for every role and scope (CLAUDE.md requires them).
- **Risk:** it widens who can see a student. That is a privacy decision, not a refactor.

### B. One counselor in several workspaces

- **Model:** a `CounselorMembership(user, school)` table plus an "active workspace" switcher.
- **Why it is large:** everything school-scoped assumes one school per user:
  - `tenant_school()` and `school_staff()`
  - seat counting
  - per-school message channels
  - the `school` field on audit events
  - the deactivated-school lockout
- **Effort and risk:** L (more than a week) and a high regression risk.
- **What works today with no code:** one account per school (different usernames), or one **Center** workspace
  (no counselor limit) that holds those students.

### C. The school adds its own counselors (replaced by the 2026-10-06 decision)

- **API:** let the `organization` role create counselors for its own school only. Reuse the existing seat lock
  (`entitlements.check(school, 'max_counselors')`), the temporary-credential flow and the audit event
  `counselor.created`. The existing `organization_accounts` plan feature can gate it.
- **UI:** an "Add counselor" action on the organization's people page.
- **Effort:** S–M (2–3 days).
- **Risk:** low. Seats and the one-time password flow already exist.

## 4. Recommendation

1. ~~Build C first.~~ Decided otherwise: the admin adds counselors, and the school edits them (issue #52).
2. **Then build a narrow A.** One lead counselor (`assigned_counselor`) plus shared counselors from the same
   workspace.
   - Shared counselors read the student's records and review submissions.
   - Parent invites and student messages stay with the lead.
3. **Do not build B now.** Use one account per school, or a Center workspace, until real demand exists. D6 (the
   counselor model) decides this.

## 5. Decisions needed

| ID | Question | Options |
| --- | --- | --- |
| SC1 | What does a shared counselor see? | Everything the lead sees / records and reviews but not private notes, messages and shared essays |
| SC2 | Who adds a shared counselor? | Product admin / school organization / the lead counselor |
| SC3 | Does a shared counselor take a seat (`max_counselors`)? | Yes / no / only when outside the workspace |
| SC4 | How is a Naseeb expert who joins a school billed? | Tied to D4 and D6 |
