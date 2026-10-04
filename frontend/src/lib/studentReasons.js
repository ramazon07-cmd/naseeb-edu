// "Why they need you" (Students page, Home, Student 360) — derived entirely from
// fields /api/students/ already returns (see progress.py/serializers/students.py:
// tasks_overdue, missions_overdue, documents_missing, to_review_total,
// user_detail.last_login). No per-student extra fetch. Translation-free like
// reviewQueue.js/meetings.js — the caller turns a reason into words
// (counselorUi.jsx reasonText).
const QUIET_DAYS = 14;

const daysSince = (value, now) => value ? Math.floor((now - new Date(value)) / 86400000) : null;

// Ordered most urgent first; a student can show more than one. "danger" reasons
// are what makes a student "need you"; a review or a quiet spell is not that.
export function studentReasons(student, now = new Date()) {
  const reasons = [];
  if (student.tasks_overdue > 0) reasons.push({ key: 'late_task', tone: 'danger', countPattern: '{n} late task|{n} late tasks', count: student.tasks_overdue });
  if (student.missions_overdue > 0) reasons.push({ key: 'late_mission', tone: 'danger', countPattern: '{n} late mission|{n} late missions', count: student.missions_overdue });
  if (student.documents_missing > 0) reasons.push({ key: 'missing_document', tone: 'danger', count: student.documents_missing, title: student.documents_missing === 1 ? student.missing_document_title : '' });
  if (student.to_review_total > 0) reasons.push({ key: 'to_review', tone: 'warning', countPattern: '{n} to review|{n} to review', count: student.to_review_total });
  const quietDays = daysSince(student.user_detail?.last_login, now);
  if (quietDays !== null && quietDays >= QUIET_DAYS) reasons.push({ key: 'quiet', tone: 'muted', quietDays });
  return reasons;
}

export const needsAttention = (reasons) => reasons.some((reason) => reason.tone === 'danger');
export const isQuiet = (reasons) => reasons.some((reason) => reason.key === 'quiet');
export const isOnTrack = (reasons) => reasons.length === 0;

// Most urgent first: how many things are late or missing, then work to review, then a quiet spell.
export const urgency = (reasons) => reasons.filter((reason) => reason.tone === 'danger').length * 100
  + (reasons.some((reason) => reason.key === 'to_review') ? 10 : 0) + (isQuiet(reasons) ? 1 : 0);
