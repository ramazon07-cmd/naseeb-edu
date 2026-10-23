import test from 'node:test';
import assert from 'node:assert/strict';
import { documentStatus, hasSubmission, opensInTab } from '../src/lib/reviewSubmission.js';

test('a document needs a file or a Google Docs link', () => {
  assert.equal(hasSubmission('document', { has_file: false, google_docs_url: '' }), false);
  assert.equal(hasSubmission('document', { has_file: true }), true);
  assert.equal(hasSubmission('document', { has_file: false, google_docs_url: 'https://docs.google.com/x' }), true);
});

test('a task needs an answer, a file or a link', () => {
  assert.equal(hasSubmission('task', { student_response: '  ', has_submission_file: false, submission_url: '' }), false);
  assert.equal(hasSubmission('task', { student_response: 'Done' }), true);
  assert.equal(hasSubmission('task', { has_submission_file: true }), true);
  assert.equal(hasSubmission('task', { submission_url: 'https://example.com' }), true);
  assert.equal(hasSubmission('task', { submission_essay_detail: { id: 7, title: 'My essay', word_count: 10 } }), true);
  assert.equal(hasSubmission('task', { submission_essay_detail: { id: 7, word_count: 0 } }), false, 'An emptied essay is not proof');
  assert.equal(hasSubmission('task', { submission_essay: 7, submission_essay_detail: null }), false, 'An unavailable essay is not proof');
});

test('an achievement needs its proof file; a mission is unchanged', () => {
  assert.equal(hasSubmission('portfolio', { has_proof_file: false, description: 'Won' }), true);
  assert.equal(hasSubmission('portfolio', { has_proof_file: true }), true);
  assert.equal(hasSubmission('roadmap', { reflection: '' }), true);
  assert.equal(hasSubmission('document', null), false);
});

test('only PDFs and plain images open in a new tab', () => {
  assert.equal(opensInTab('application/pdf'), true);
  assert.equal(opensInTab('image/png; charset=binary'), true);
  assert.equal(opensInTab('image/svg+xml'), false);
  assert.equal(opensInTab('text/html'), false);
  assert.equal(opensInTab(''), false);
});

test('an empty uploaded or reviewing document reads as required', () => {
  assert.equal(documentStatus({ status: 'uploaded', has_file: false, google_docs_url: '' }), 'required');
  assert.equal(documentStatus({ status: 'reviewing', has_file: false }), 'required');
  assert.equal(documentStatus({ status: 'uploaded', has_file: true }), 'uploaded');
  assert.equal(documentStatus({ status: 'uploaded', google_docs_url: 'https://docs.google.com/x' }), 'uploaded');
  assert.equal(documentStatus({ status: 'approved', has_file: false }), 'approved');
});
