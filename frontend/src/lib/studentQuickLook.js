// What the Students page's quick look lists for one student, from the records
// GET /api/<records>/?student=<id> returns. Same rules as the server
// (progress.py, counselor_summary.py): open work past its due date is late,
// a "required" document (or one marked uploaded with no file or link) is missing, submitted work waits for the counselor,
// and a week runs Monday to Sunday. Translation-free like studentReasons.js;
// the component turns each item into words.
const OPEN_TASK = ['todo', 'in_progress', 'late'];
const APPLICATION_DONE = ['submitted', 'accepted', 'rejected', 'waitlisted'];
const OPEN_LETTER = ['requested', 'drafting'];
const DOCUMENT_REVIEW = ['uploaded', 'reviewing'];
const attached = (doc) => Boolean(doc.has_file || doc.google_docs_url);

const pad = (value) => String(value).padStart(2, '0');
const keyOf = (date) => `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
const dayOnly = (value) => (value ? String(value).slice(0, 10) : '');

// [Monday, Sunday] of the week holding `today` ('YYYY-MM-DD').
export function weekOf(today) {
  const [year, month, day] = today.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const monday = new Date(date);
  monday.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return [keyOf(monday), keyOf(sunday)];
}

// Most urgent first: late work, missing documents, then work to review.
export function attentionItems(records, today) {
  const items = [];
  for (const task of records.tasks || []) {
    if (OPEN_TASK.includes(task.status) && task.due_date && task.due_date < today) items.push({ key: `task-${task.id}`, kind: 'late_task', title: task.title, due: task.due_date });
  }
  for (const doc of records.documents || []) {
    if (doc.status === 'required' || (DOCUMENT_REVIEW.includes(doc.status) && !attached(doc))) items.push({ key: `doc-${doc.id}`, kind: 'missing_document', title: doc.title });
  }
  for (const task of records.tasks || []) {
    if (task.status === 'submitted') items.push({ key: `review-task-${task.id}`, kind: 'review', title: task.title });
  }
  for (const mission of records['roadmap-missions'] || []) {
    if (mission.status === 'submitted') items.push({ key: `review-mission-${mission.id}`, kind: 'review', title: mission.title });
  }
  for (const doc of records.documents || []) {
    if (DOCUMENT_REVIEW.includes(doc.status) && attached(doc)) items.push({ key: `review-doc-${doc.id}`, kind: 'review', title: doc.title });
  }
  // Portfolio waiting for the counselor (?awaiting_review=true): not verified, not sent back.
  for (const item of records.achievements || []) {
    if (!item.verified && !item.counselor_comment) items.push({ key: `review-achievement-${item.id}`, kind: 'review', title: item.title });
  }
  return items;
}

// Open, dated work due this week (Monday to Sunday), soonest first.
export function weekDeadlines(records, today) {
  const [start, end] = weekOf(today);
  const items = [];
  const add = (kind, id, title, due) => {
    const day = dayOnly(due);
    if (day && day >= start && day <= end) items.push({ key: `${kind}-${id}`, kind, title, due: day, late: day < today });
  };
  for (const task of records.tasks || []) if (OPEN_TASK.includes(task.status)) add('task', task.id, task.title, task.due_date);
  for (const item of records.applications || []) if (!APPLICATION_DONE.includes(item.status)) add('application', item.id, item.university_detail?.name || '', item.deadline);
  for (const letter of records.recommendations || []) if (OPEN_LETTER.includes(letter.status)) add('letter', letter.id, letter.recommender_name || '', letter.deadline);
  return items.sort((a, b) => a.due.localeCompare(b.due) || a.key.localeCompare(b.key));
}
