import test from 'node:test';
import assert from 'node:assert/strict';
import { clearDraft, fieldErrorsFrom, firstStepWithError, loadDraft, saveDraft } from '../src/lib/onboardingDraft.js';

function memoryStorage() {
  const map = new Map();
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k) };
}

test('a draft round-trips per key and a corrupt or foreign draft is ignored', () => {
  const storage = memoryStorage();
  saveDraft(storage, 'draft:7', { first_name: 'Aziza' }, 3);
  assert.deepEqual(loadDraft(storage, 'draft:7'), { form: { first_name: 'Aziza' }, step: 3 });
  assert.equal(loadDraft(storage, 'draft:8'), null);
  storage.setItem('draft:9', '{broken');
  assert.equal(loadDraft(storage, 'draft:9'), null);
  storage.setItem('draft:10', JSON.stringify({ form: {}, step: 99 }));
  assert.equal(loadDraft(storage, 'draft:10').step, 0);
  clearDraft(storage, 'draft:7');
  assert.equal(loadDraft(storage, 'draft:7'), null);
});

test('server errors map to fields and to the first step that shows them', () => {
  const errors = fieldErrorsFrom({ gpa: ['Too high.'], honors: [{}, { role: ['Required.'] }], non_field_errors: ['x'] });
  assert.deepEqual(errors, { gpa: 'Too high.', honors: 'Required.' });
  assert.equal(firstStepWithError(errors), 1);
  assert.equal(firstStepWithError({ activities: 'x' }), 5);
  assert.equal(firstStepWithError({}), -1);
  assert.deepEqual(fieldErrorsFrom('<html>'), {});
});
