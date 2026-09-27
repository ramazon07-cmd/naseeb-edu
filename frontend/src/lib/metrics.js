// Client-side twins of the backend metric rules (see docs/metrics.md). The
// numbers themselves come from the API; these only pick and order records.

// Work the student still owes. Submitted work waits on the reviewer.
export const OPEN_TASK_STATUSES = ['todo', 'in_progress', 'late'];
// Sent to the university; any decision comes only after that.
export const SUBMITTED_APPLICATION_STATUSES = ['submitted', 'accepted', 'rejected', 'waitlisted'];
export const MAX_LEVEL = 100;

const PRIORITY_RANK = { urgent: 0, high: 1, medium: 2, low: 3 };
const NO_DEADLINE = '9999-12-31';

// Sum of a `{status: count}` map such as task_status_counts.
export const countTotal = (counts) => Object.values(counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0);

export const isOpenTask = (task) => OPEN_TASK_STATUSES.includes(task?.status);

// Earliest deadline first (overdue work leads), then the most urgent, then
// the oldest: the same order as the backend's Task ordering.
export function compareTasksByDeadline(a, b) {
  const byDate = String(a.due_date || NO_DEADLINE).localeCompare(String(b.due_date || NO_DEADLINE));
  if (byDate) return byDate;
  const byPriority = (PRIORITY_RANK[a.priority] ?? 4) - (PRIORITY_RANK[b.priority] ?? 4);
  return byPriority || (a.id ?? 0) - (b.id ?? 0);
}

export const nextPriorities = (tasks = []) => tasks.filter(isOpenTask).sort(compareTasksByDeadline);

export const nextLevel = (student) => {
  const level = student?.level ?? 1;
  return student?.level_up_pending ? student.eligible_level : Math.min(MAX_LEVEL, level + 1);
};

// A mission is locked while its prerequisite is not approved. The API sends
// the prerequisite's status, so a paged list needs no other page to decide.
export function prerequisiteStatus(item, missions = []) {
  if (!item?.prerequisite) return null;
  if (item.prerequisite_status) return item.prerequisite_status;
  return missions.find((candidate) => candidate.id === item.prerequisite)?.status ?? null;
}

export const isMissionLocked = (item, missions) => {
  const status = prerequisiteStatus(item, missions);
  return status !== null && status !== 'completed';
};

const whole = (value) => Math.max(0, Number(value) || 0);
const clampPercent = (value) => Math.min(100, whole(value));

// Every progress number a student sees, straight from the API fields in
// docs/metrics.md: overall (tasks + roadmap), roadmap (all missions) and the
// current level. The browser never recomputes them from a paged list.
export function studentProgress(student) {
  return {
    overallPercent: clampPercent(student?.journey_progress_percent),
    roadmapPercent: clampPercent(student?.roadmap_progress_percent),
    missionsApproved: whole(student?.roadmap_stars),
    missionsTotal: countTotal(student?.roadmap_status_counts),
    levelApproved: whole(student?.level_missions_approved),
    levelTotal: whole(student?.level_missions_total),
    applicationsTotal: whole(student?.applications_total),
    applicationsSubmitted: whole(student?.applications_submitted),
    applicationsAccepted: whole(student?.applications_accepted),
    achievementsTotal: whole(student?.achievements_total),
  };
}
