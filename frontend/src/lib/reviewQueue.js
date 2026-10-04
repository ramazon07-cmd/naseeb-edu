// Client-side twin of "things waiting for a counselor's review" (see the product
// vision doc, S3.4.2 "Today's queue"). Staff never bulk-load tasks/documents/
// roadmap missions/achievements (see workspaceResources.js) — each list here is
// already fetched server-filtered to its "needs review" state by useReviewQueue,
// so this only shapes and orders what it is given.

// `endpoint`/`filters` are what useReviewQueue fetches with; `label` is the
// row's tag, `pill` its filter pill, `when` the "submitted 2 days ago" pattern
// (a t() key with a {when} slot); `countPattern` is a raw "{n} x|{n} xs"
// string for tp() — this file stays translation-free like metrics.js/meetings.js,
// so the caller runs it through tp().
export const REVIEW_SOURCES = [
  { kind: 'task', listKey: 'tasks', endpoint: 'tasks', filters: { status: 'submitted' }, label: 'Task', pill: 'Tasks', when: 'submitted {when}', countPattern: '{n} task|{n} tasks', at: (item) => item.submitted_at || item.updated_at },
  { kind: 'document', listKey: 'documents', endpoint: 'documents', filters: { awaiting_review: 'true' }, label: 'Document', pill: 'Documents', when: 'uploaded {when}', countPattern: '{n} document|{n} documents', at: (item) => item.updated_at },
  { kind: 'roadmap', listKey: 'roadmapMissions', endpoint: 'roadmap-missions', filters: { status: 'submitted' }, label: 'Roadmap', pill: 'Roadmap', when: 'submitted {when}', countPattern: '{n} mission|{n} missions', at: (item) => item.updated_at },
  { kind: 'portfolio', listKey: 'achievements', endpoint: 'achievements', filters: { awaiting_review: 'true' }, label: 'Portfolio', pill: 'Portfolio', when: 'added {when}', countPattern: '{n} portfolio item|{n} portfolio items', at: (item) => item.created_at },
];

export const REVIEW_SOURCE = Object.fromEntries(REVIEW_SOURCES.map((source) => [source.kind, source]));

// `lists`: { [listKey]: items[] }, one already-filtered page per source. Oldest
// first, across every source — the same order the Review mock uses.
// `id` is a composite (kind-recordId, unique across every source, for React
// keys); `recordId`/`endpoint` are what a PATCH or action call needs, `record`
// the API row for the detail pane.
export function mergeReviewQueue(lists) {
  return REVIEW_SOURCES.flatMap(({ kind, listKey, endpoint, label, when, countPattern, at }) => (lists[listKey] || []).map((item) => ({
    id: `${kind}-${item.id}`,
    recordId: item.id,
    kind, label, endpoint, when, countPattern,
    title: item.title,
    studentId: item.student,
    studentName: item.student_name,
    at: at(item),
    record: item,
  }))).sort((a, b) => new Date(a.at) - new Date(b.at));
}
