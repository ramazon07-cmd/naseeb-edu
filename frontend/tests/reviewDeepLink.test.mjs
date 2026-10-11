import assert from 'node:assert/strict';
import test from 'node:test';
import { buildPath, parsePath } from '../src/lib/routes.js';
import { awaitingReview, deepLinkStep, linkedReviewItem, mergeReviewQueue, parseReviewItemId } from '../src/lib/reviewQueue.js';

test('a Home review row links to that item in Review', () => {
  assert.equal(buildPath({ page: 'review', params: { item: 'document-12' } }), '/review?item=document-12');
  assert.deepEqual(parsePath('/review'), { page: 'review', params: {} });
});

test('a malformed review item falls back to the bare queue', () => {
  for (const item of ['document-0', '12', 'doc/../x', '<b>', undefined]) {
    assert.equal(buildPath({ page: 'review', params: { item } }), '/review', String(item));
  }
});

test('review links name a kind and a record id', () => {
  assert.deepEqual(parseReviewItemId('document-12'), { kind: 'document', recordId: 12 });
  for (const id of ['essay-3', 'task-0', 'task-', 'task-1x', null, undefined, '']) assert.equal(parseReviewItemId(id), null, String(id));
});

test('a linked item opens only itself: found, wait for the lists, or fetch it alone', () => {
  const items = mergeReviewQueue({ tasks: [{ id: 1, title: 'A', submitted_at: '2026-10-01T00:00:00Z' }] });
  assert.equal(deepLinkStep('task-1', items, false), 'found');
  assert.equal(deepLinkStep('task-2', items, false), 'wait');
  // Loaded pages lack it (they are ordered by creation, Home by submission): fetch that record.
  assert.equal(deepLinkStep('task-2', items, true), 'fetch');
  assert.equal(deepLinkStep('task-2', [], true), 'fetch');
  assert.equal(deepLinkStep('bogus', items, true), 'gone');
});

test('a fetched record is shown only while it still waits for review', () => {
  const task = { id: 9, title: 'Essay outline', student: 4, student_name: 'Ali', status: 'submitted', submitted_at: '2026-10-02T00:00:00Z' };
  const item = linkedReviewItem('task-9', task);
  assert.equal(item.id, 'task-9');
  assert.equal(item.endpoint, 'tasks');
  assert.equal(item.recordId, 9);
  assert.equal(item.at, task.submitted_at);
  assert.equal(linkedReviewItem('task-9', { ...task, status: 'approved' }), null);
  assert.equal(linkedReviewItem('task-8', task), null);
  assert.equal(linkedReviewItem('task-9', null), null);
  assert.equal(awaitingReview('document', { status: 'reviewing', has_file: true }), true);
  assert.equal(awaitingReview('document', { status: 'uploaded', google_docs_url: 'https://docs.google.com/document/d/x' }), true);
  // Nothing attached: the server leaves it out of ?awaiting_review=true too.
  assert.equal(awaitingReview('document', { status: 'uploaded', has_file: false, google_docs_url: '' }), false);
  assert.equal(awaitingReview('document', { status: 'approved' }), false);
  assert.equal(awaitingReview('roadmap', { status: 'submitted' }), true);
  assert.equal(awaitingReview('portfolio', { verified: false, counselor_comment: '' }), true);
  assert.equal(awaitingReview('portfolio', { verified: false, counselor_comment: 'Add proof' }), false);
  assert.equal(awaitingReview('portfolio', { verified: true }), false);
});
