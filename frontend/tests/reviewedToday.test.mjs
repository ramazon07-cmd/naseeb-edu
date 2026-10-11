import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { createReviewedTodayState, mergeReviewedToday, reviewedTodayRows, settleLocal } = await import('../src/lib/reviewedToday.js');
const { createLatestRequest } = await import('../src/lib/latestRequest.js');

const item = { id: 'document-7', kind: 'document', recordId: 7, title: 'Transcript', studentId: 3, studentName: 'Aziza Karimova' };
const serverRow = (id, extra = {}) => ({ id, kind: 'document', record_id: 7, decision: 'approved', title: 'Transcript', at: '2026-10-10T20:30:01Z', ...extra });

test('a decision made here shows at once, shaped like a server row', () => {
  const state = createReviewedTodayState();
  const local = state.local(item, 'approved');
  assert.equal(local.pending, true);
  assert.deepEqual(
    mergeReviewedToday([], [local]).map((row) => [row.kind, row.record_id, row.decision, row.title, row.student_name]),
    [['document', 7, 'approved', 'Transcript', 'Aziza Karimova']],
  );
});

test('the reply to a request started after the decision replaces the local row', () => {
  const state = createReviewedTodayState();
  const local = [state.local(item, 'approved')];
  const mark = state.mark();
  assert.deepEqual(settleLocal(local, mark), []);
  assert.deepEqual(mergeReviewedToday([serverRow(40)], settleLocal(local, mark)).map((row) => row.id), [40]);
});

test('an approve that wrote nothing (already approved) drops out with the next reply', () => {
  const state = createReviewedTodayState();
  const local = [state.local(item, 'approved')];
  const mark = state.mark();
  assert.deepEqual(mergeReviewedToday([], settleLocal(local, mark)), []);
});

test('a reply to a request started before a decision keeps that decision', () => {
  const state = createReviewedTodayState();
  const mark = state.mark();
  const local = [state.local(item, 'sent_back')];
  assert.deepEqual(settleLocal(local, mark), local);
  assert.deepEqual(mergeReviewedToday([serverRow(41)], settleLocal(local, mark)).map((row) => row.id), [local[0].id, 41]);
});

test('matching ignores clocks: a server stamp hours off still settles the row', () => {
  const state = createReviewedTodayState();
  const local = [state.local(item, 'approved', new Date('2026-10-10T08:00:00Z'))];
  const mark = state.mark();
  assert.deepEqual(mergeReviewedToday([serverRow(42, { at: '2026-10-10T19:01:00Z' })], settleLocal(local, mark)).map((row) => row.id), [42]);
});

test('newest local decisions first, then the server order', () => {
  const state = createReviewedTodayState();
  const first = state.local(item, 'approved');
  const second = state.local({ ...item, id: 'task-2', kind: 'task', recordId: 2 }, 'sent_back');
  assert.deepEqual(mergeReviewedToday([serverRow(43), serverRow(44)], [first, second]).map((row) => row.id), [second.id, first.id, 43, 44]);
});

test('replies come wrapped or unwrapped', () => {
  assert.deepEqual(reviewedTodayRows([serverRow(1)]).map((row) => row.id), [1]);
  assert.deepEqual(reviewedTodayRows({ results: [serverRow(2)], since: 'x' }).map((row) => row.id), [2]);
  assert.deepEqual(reviewedTodayRows(null), []);
});

test('an older reply that arrives last does not overwrite a newer one', () => {
  const latest = createLatestRequest();
  let shown = null;
  const older = latest.start();
  const newer = latest.start();
  if (newer()) shown = 'newer';
  if (older()) shown = 'older';
  assert.equal(shown, 'newer');
});
