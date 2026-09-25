# Metrics: one definition for every number

The backend computes every number shown on the dashboards. The frontend only
formats them. The code lives in `backend/apps/admissions/progress.py`
(per student: `ProgressStats`; per scope: `summarize_progress`, which gives
the same results in SQL). Every flow below is covered end to end in
`backend/apps/admissions/tests/test_journeys_e2e.py`.

## Rounding

A percentage is `part / whole × 100`, **rounded half up to a whole number**
and computed with exact integer arithmetic: `(200·part + whole) // (2·whole)`.
It is 0 when `whole` is 0. So 1 of 8 is 13%, 23 of 40 is 58%, and 2 of 3 is
67%. This matches what `Math.round` shows in the browser. Averages over
students use the same rule on the sum of the per-student whole-number
percentages.

## Statuses

| Record | Statuses | Counts as done | Still owed by the student ("open") |
|---|---|---|---|
| Task | todo, in_progress, submitted, approved, late | approved | todo, in_progress, late |
| Roadmap mission | planned, in_progress, submitted, completed | completed (approved by staff) | planned, in_progress |
| Application | researching, shortlisted, applying, submitted, accepted, rejected, waitlisted | submitted, accepted, rejected, waitlisted | — |
| Document | required, uploaded, reviewing, approved, rejected | approved | required, rejected |
| Recommendation letter | requested, drafting, submitted, approved | submitted, approved | — |

Only staff record an approval. A student can resubmit work, but can never
move a record out of an approved state. The rules:

* An approved task or letter is locked for the student.
* A document under review or approved goes back to `uploaded` only when the
  student uploads a new file or link.
* When the student edits an activity, honor, achievement, research, project
  or internship that a counselor verified, it loses its `verified` badge.

## Per student (`/api/students/`, Student 360, parent portal)

| Field | Label in the UI | Formula |
|---|---|---|
| `progress_percent` | Application readiness | `readiness_items_done / readiness_items_total`. Items are all tasks, applications, documents and recommendation letters; the "done" column above decides which are finished. |
| `readiness_items_done`, `readiness_items_total` | "x of y items finished" | The two counts above. |
| `task_progress_percent` | Task progress | Weighted mean over all tasks: todo 0, late 0, in_progress 40, submitted 80, approved 100. |
| `roadmap_progress_percent` | Roadmap progress | completed missions / all missions. |
| `roadmap_stars` | Stars | Number of completed (approved) missions: one star per approved step. |
| `level_missions_approved`, `level_missions_total` | "This level: x of y" | Completed missions and all missions whose `level` is the student's approved `level`. |
| `applications_total` | Universities on your list | All applications. |
| `applications_submitted` | Submitted | Applications that are submitted or have a decision (the "done" column above). |
| `applications_accepted` | Accepted | Applications whose status is `accepted`. |
| `achievements_total` | Achievements | Achievement records plus honor records, verified or not. |
| `journey_progress_percent` | Overall journey | The rounded mean of task and roadmap progress, `(task + roadmap + 1) // 2`. If the student has only tasks or only missions, it is that one number; with neither it is 0. |
| `is_at_risk` | Needs attention | Any late task (see below), **or** any open mission past its due date. Submitted work is waiting on the reviewer, so it is never late. |
| `task_status_counts`, `roadmap_status_counts` | "0/4 Tasks" etc. | A count for every status (zeros included). |
| `xp_total` | XP | The sum of approval awards. Each approved piece of work earns XP at most once. A task earns 25/50/75/100 for low/medium/high/urgent priority; a task the student set themselves earns 0; a mission earns 75. |
| `level` | Level | The approved level. It only changes when a teacher or counselor approves it. |
| `eligible_level` | — | The highest level `L` (maximum 100) with `xp_total ≥ 100·L·(L−1)/2`. Reaching Level 2 needs 100 XP, Level 3 needs 300, Level 4 needs 600. |
| `level_up_pending` | "Level N approval pending" | `eligible_level > level`. |
| `next_level_xp` | Next level | The XP needed to reach `level + 1` (a total, not what is left). |
| `xp_progress_percent` | — | Progress from the current level's threshold to the next one; 100 while a level-up is pending. |
| `profile_readiness.percent` | Profile ready | Answered readiness items / 12, from the student's own profile row (no other records). The items: photo, graduation year, guardian name and contact, school with country and city, GPA, an IELTS answer other than "not taken yet", the same for the SAT, target countries, areas of interest, personal story, at least one activity, at least one honor (`onboarding.PROFILE_READINESS_ITEMS`). |
| `profile_readiness.missing` | "To raise it: …" | The unanswered items in that order, each with the profile section that holds it. |

A task is `is_overdue` when it is open and its due date is before today, in
the server's time zone.
This is the one meaning of a *late* task: the student still owes the work
and it is past due. `is_at_risk`, `tasks_late` and the "Late tasks require
attention" alert all count exactly these tasks (`progress.late_tasks`); the
`late` status on its own, with a due date still ahead, does not make a task late.

## Dashboard (`/api/dashboard/stats/`)

The scope is the students the user can see (see `scoping.py`), without
deactivated students. For a counselor that means their assigned students in
their own school; a student who moves to another school drops out of it.

| Field | Label | Formula |
|---|---|---|
| `students_total` | Students | Active students in scope. |
| `average_progress`, `average_task_progress`, `average_roadmap_progress`, `average_journey_progress` | Task/Roadmap progress | Half-up mean of the per-student values. A student with no records counts as 0. |
| `students_at_risk` | Need attention | Students with `is_at_risk`. |
| `tasks_total` | — | All tasks in scope. |
| `tasks_late` | — | Open tasks past their due date. |
| `tasks_due_week` | — | Open tasks due from today through today + 7 days. |
| `applications_submitted` | — | Applications that are submitted or have a decision. |
| `documents_pending_review` | — | Documents that are uploaded or reviewing. |
| `essays_need_revision` | — | Essays not in the trash whose status is needs_revision. |

The summary is cached per scope. Every save or delete of a task, mission,
application, document, letter, student profile, school, or of a user's
active flag, school or role clears it at once.

## Student dashboard and roadmap

Two different numbers, each always with its own label:

* **Overall progress** is `journey_progress_percent` (tasks and roadmap together).
* **Roadmap progress** is `roadmap_progress_percent`, shown with
  "Roadmap: `roadmap_stars` of all missions approved". The dashboard's
  Roadmap tile and the Level path header both show this number, and the star
  count is the same `roadmap_stars`.
* **This level** counts only the current level:
  `level_missions_approved` of `level_missions_total`.

The Applications tile shows `applications_total`, `applications_submitted`,
`applications_accepted` and `achievements_total`, never counts of the
records loaded in the browser (those lists are paged).

## Lists on the student dashboard

* **Next priorities**: open tasks, earliest due date first, then the most
  urgent priority, then the oldest. Submitted and approved tasks are left out.
* **Deadline radar** (staff): the six open tasks due first (`/api/tasks/?open=true&ordering=due`).
* **Applications tile**: "Submitted" is `applications_submitted` (submitted
  applications and those with a decision).

## Notifications (`generate_notifications`, daily)

| Title | Condition |
|---|---|
| Late tasks require attention | At least one open task is past its due date. |
| Required documents are missing | At least one document is `required` or `rejected`. |
| University deadline approaching | An application that is not yet submitted has its deadline within 14 days. |

When a condition no longer holds, its alert is marked read.

## Messaging

A direct-chat channel's `unread_count` counts messages from other people
created after the reader's `last_read_at`. Opening the chat (`mark-read`) or
sending a message in it moves `last_read_at` forward. `unread_total` in
`/api/message-channels/overview/` is the sum over the user's channels.

## Meetings (`/api/bookings/`)

| Status | Meaning |
|---|---|
| pending | Requested by the student (or rescheduled), waiting for the staff participant. |
| approved | Confirmed by the participant. |
| rejected | Declined by the participant. |
| completed | Held; marked by the participant. |
| cancelled | Called off before it started, by the student or the participant. |

A request is `is_expired` when it is still `pending` at its start time. The
flag is derived on every read, never stored, so no job has to run for it and
the status is unchanged: an expired request cannot be approved, cancelled or
rescheduled, and it shows in History as "Expired — not confirmed".
**Upcoming** meetings are pending or approved ones that have not started.
Cancelling and rescheduling are for pending or approved meetings that have not
started; a reschedule sets the meeting back to `pending`. Each change posts a
notification on the student's feed, which their counselor also sees.
