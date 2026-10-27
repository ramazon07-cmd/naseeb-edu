import test from 'node:test';
import assert from 'node:assert/strict';
import { settleWorkspaceRequests } from '../src/lib/settleWorkspaceRequests.js';
import { createKeyedLatest } from '../src/lib/latestRequest.js';

test('dashboard data is published while an unrelated request is still pending', async () => {
  let finishTickets;
  const published = [];
  const done = settleWorkspaceRequests([
    ['tickets', () => new Promise((resolve) => { finishTickets = resolve; })],
    ['dashboard', async () => ({ students: 12 })],
  ], (key, result) => published.push([key, result]));
  await Promise.resolve();
  assert.deepEqual(published, [['dashboard', { status: 'fulfilled', value: { students: 12 } }]]);
  finishTickets([]);
  const results = await done;
  assert.deepEqual(published.map(([key]) => key), ['dashboard', 'tickets']);
  assert.deepEqual(results.map((result) => result.value), [[], { students: 12 }]);
});

test('one failure does not prevent other resources arriving, including synchronous failures', async () => {
  const error = new Error('offline');
  const published = [];
  const results = await settleWorkspaceRequests([
    ['tickets', () => { throw error; }],
    ['dashboard', async () => ({ students: 12 })],
  ], (key, result) => published.push([key, result.status]));
  assert.deepEqual(published, [['tickets', 'rejected'], ['dashboard', 'fulfilled']]);
  assert.equal(results[0].reason, error);
  assert.equal(results[1].status, 'fulfilled');
});

test('late data can still be discarded after a newer load or sign-out', async () => {
  const latest = createKeyedLatest();
  const current = latest.start(['dashboard']);
  let finish;
  const published = [];
  const done = settleWorkspaceRequests([
    ['dashboard', () => new Promise((resolve) => { finish = resolve; })],
  ], (key, result) => { if (current(key)) published.push(result); });
  latest.cancelAll();
  finish({ students: 12 });
  await done;
  assert.deepEqual(published, []);
});
