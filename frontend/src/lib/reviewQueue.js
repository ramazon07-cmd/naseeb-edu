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
  { kind: 'portfolio', listKey: 'achievements', endpoint: 'achievements', filters: { awaiting_review: 'true' }, label: 'Portfolio', pill: 'Portfolio', when: 'added {when}', countPattern: '{n} portfolio item|{n} portfolio items', at: (item) => item.created_at },
];

// Every source is paged oldest first (RECORD_ORDERING 'created' on the server).
export const REVIEW_ORDERING = 'created';

export const REVIEW_SOURCE = Object.fromEntries(REVIEW_SOURCES.map((source) => [source.kind, source]));

// The approve call for each kind, shared by Review and Home. `api` is passed in
// so this file stays free of the network layer.
const APPROVE = {
  task: (api, id, note) => api.approveTask(id, note),
  document: (api, id, note) => api.approveRecord('documents', id, note),
  roadmap: (api, id, note) => api.approveRoadmapMission(id, note),
  portfolio: (api, id, note) => api.approveRecord('achievements', id, note),
};

export const canApprove = (kind) => Boolean(APPROVE[kind]);

export function approveReviewItem(api, kind, recordId, note = '') {
  if (!APPROVE[kind] || !recordId) return Promise.reject(new Error(`Cannot approve ${kind}`));
  return Promise.resolve(APPROVE[kind](api, recordId, note));
}

// `lists`: { [listKey]: items[] }, one already-filtered page per source. Oldest
// first, across every source — the same order the Review mock uses.
// `id` is a composite (kind-recordId, unique across every source, for React
// keys); `recordId`/`endpoint` are what a PATCH or action call needs, `record`
// the API row for the detail pane.
export function reviewItem({ kind, endpoint, label, when, countPattern, at }, item) {
  return {
    id: `${kind}-${item.id}`,
    recordId: item.id,
    kind, label, endpoint, when, countPattern,
    title: item.title,
    studentId: item.student,
    studentName: item.student_name,
    at: at(item),
    record: item,
  };
}

export function mergeReviewQueue(lists) {
  return REVIEW_SOURCES.flatMap((source) => (lists[source.listKey] || []).map((item) => reviewItem(source, item)))
    .sort((a, b) => new Date(a.at) - new Date(b.at));
}

// `/review?item=kind-id` (Home's rows): { kind, recordId }, or null when malformed.
export function parseReviewItemId(id) {
  const match = /^([a-z]+)-([1-9]\d*)$/.exec(String(id ?? ''));
  return match && REVIEW_SOURCE[match[1]] ? { kind: match[1], recordId: Number(match[2]) } : null;
}

// The same "needs review" test each source's list filter applies on the server.
const AWAITING = {
  task: (record) => record.status === 'submitted',
  document: (record) => ['uploaded', 'reviewing'].includes(record.status) && Boolean(record.has_file || record.google_docs_url),
  roadmap: (record) => record.status === 'submitted',
  portfolio: (record) => record.verified === false && !record.counselor_comment,
};

export const awaitingReview = (kind, record) => Boolean(record && AWAITING[kind]?.(record));

/**
 * What Review does with a linked item. Lists come oldest-created first while
 * Home picks the oldest submissions, so a linked item may sit on a page not
 * loaded yet: 'found' (in the list), 'wait' (lists still loading), 'fetch'
 * (load that one record), 'gone' (malformed link). Never another item.
 */
export function deepLinkStep(itemId, items, loaded) {
  if (!parseReviewItemId(itemId)) return 'gone';
  if (items.some((item) => item.id === itemId)) return 'found';
  return loaded ? 'fetch' : 'wait';
}

// A fetched record as a queue item, or null when it no longer waits for review.
export function linkedReviewItem(itemId, record) {
  const parsed = parseReviewItemId(itemId);
  if (!parsed || !record || Number(record.id) !== parsed.recordId || !awaitingReview(parsed.kind, record)) return null;
  return reviewItem(REVIEW_SOURCE[parsed.kind], record);
}
