import test from 'node:test';
import assert from 'node:assert/strict';
import {
  assessmentLockReason, isRetryableSaveError, loadPendingAttempts, mergeServerAnswers, saveRetryDelay, storePendingAttempts,
} from '../src/lib/assessmentSync.js';

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: (key) => data.delete(key), data };
}

const payload = { challenge: 'personality', answers: { p1: 3 }, scores: {}, completed_at: '2026-09-25T10:00:00.000Z' };

test('pending results survive a reload and drop malformed entries', () => {
  const storage = memoryStorage();
  storePendingAttempts(storage, 'k', { personality: payload });
  assert.deepEqual(loadPendingAttempts(storage, 'k'), { personality: payload });
  storePendingAttempts(storage, 'k', {});
  assert.equal(storage.data.has('k'), false, 'an empty queue is removed');
  const messy = memoryStorage({ k: JSON.stringify({ personality: payload, interests: { challenge: 'other' }, subjects: null }) });
  assert.deepEqual(loadPendingAttempts(messy, 'k'), { personality: payload });
  assert.deepEqual(loadPendingAttempts(memoryStorage({ k: 'not json' }), 'k'), {});
  assert.deepEqual(loadPendingAttempts(null, 'k'), {});
});

test('only transient save failures are retried', () => {
  for (const status of [0, 408, 429, 500, 502, 503]) assert.equal(isRetryableSaveError({ status }), true, String(status));
  for (const status of [400, 401, 403, 404]) assert.equal(isRetryableSaveError({ status }), false, String(status));
  assert.equal(isRetryableSaveError(new TypeError('Failed to fetch')), true);
  assert.equal(isRetryableSaveError({ name: 'AbortError' }), false);
});

test('retry delay backs off with a floor and a cap', () => {
  assert.equal(saveRetryDelay(0, () => 0), 1000);
  assert.equal(saveRetryDelay(3, () => 0.5), 8000);
  assert.equal(saveRetryDelay(20, () => 0.999999), 59999);
});

test('server answers win except for results still waiting to be saved', () => {
  const local = { p1: 5, i1: 2, draft: 4 };
  const latest = { personality: { challenge: 'personality', answers: { p1: 1 } }, interests: { challenge: 'interests', answers: { i1: 4 } } };
  assert.deepEqual(mergeServerAnswers(local, latest, {}), { p1: 1, i1: 4, draft: 4 });
  assert.deepEqual(mergeServerAnswers(local, latest, { personality: payload }), { p1: 5, i1: 4, draft: 4 });
});

test('major matches unlock only from results the account holds', () => {
  const challengeKeys = ['a', 'b'];
  const base = { challengeKeys, completedKeys: ['a', 'b'], saved: { a: {}, b: {} }, pending: {}, loading: false, loadFailed: false };
  assert.equal(assessmentLockReason(base), null);
  assert.equal(assessmentLockReason({ ...base, completedKeys: ['a'] }), 'incomplete');
  assert.equal(assessmentLockReason({ ...base, loading: true }), 'loading');
  assert.equal(assessmentLockReason({ ...base, pending: { b: payload } }), 'pending');
  assert.equal(assessmentLockReason({ ...base, saved: { a: {} } }), 'unsynced', 'device-only results do not unlock');
  assert.equal(assessmentLockReason({ ...base, loadFailed: true }), 'unsynced');
});
