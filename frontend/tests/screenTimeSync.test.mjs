import test from 'node:test';
import assert from 'node:assert/strict';
import { addScreenTime, createScreenTimeSync, subtractSent } from '../src/screenTimeQueue.js';

const today = () => '2026-09-14';

function harness({ fail = false } = {}) {
  let stored = [];
  const calls = [];
  let release;
  const sync = createScreenTimeSync({
    load: () => stored,
    save: (entries) => { stored = JSON.parse(JSON.stringify(entries)); },
    today,
    send: (batch) => {
      calls.push(batch);
      return new Promise((resolve, reject) => { release = () => (fail ? reject(new Error('offline')) : resolve()); });
    },
  });
  return { sync, calls, stored: () => stored, release: () => release() };
}

test('seconds recorded while an upload is in flight are not lost (M8)', async () => {
  const h = harness();
  h.sync.record('dashboard', 40);
  const first = h.sync.flush();
  h.sync.record('dashboard', 15);   // arrives during the request
  h.sync.record('messages', 7);
  await h.sync.flush();             // overlapping flush only persists
  assert.equal(h.calls.length, 1);
  h.release();
  await first;
  assert.deepEqual(h.sync.pending(), [
    { date: '2026-09-14', page: 'dashboard', seconds: 15 },
    { date: '2026-09-14', page: 'messages', seconds: 7 },
  ]);
  assert.deepEqual(h.stored(), h.sync.pending());
});

test('a failed upload keeps everything queued', async () => {
  const h = harness({ fail: true });
  h.sync.record('tasks', 30);
  const pending = h.sync.flush();
  h.release();
  await pending;
  assert.deepEqual(h.sync.pending(), [{ date: '2026-09-14', page: 'tasks', seconds: 30 }]);
});

test('batches are capped at 300 s per entry and the remainder stays queued', async () => {
  const h = harness();
  h.sync.record('roadmap', 420);
  const pending = h.sync.flush();
  assert.equal(h.calls[0][0].seconds, 300);
  h.release();
  await pending;
  assert.deepEqual(h.sync.pending(), [{ date: '2026-09-14', page: 'roadmap', seconds: 120 }]);
});

test('pure helpers do not mutate their input', () => {
  const queue = Object.freeze([Object.freeze({ date: '2026-09-14', page: 'a', seconds: 5 })]);
  assert.deepEqual(addScreenTime(queue, '2026-09-14', 'a', 3), [{ date: '2026-09-14', page: 'a', seconds: 8 }]);
  assert.deepEqual(subtractSent(queue, [{ date: '2026-09-14', page: 'a', seconds: 5 }]), []);
});

test('after a failed upload the next attempts back off with jitter; force and success reset it', async () => {
  let time = 1_000_000;
  let fail = true;
  const calls = [];
  const sync = createScreenTimeSync({
    load: () => [], save: () => {}, today, now: () => time, random: () => 0.5,
    send: async (batch) => { calls.push(batch); if (fail) throw new Error('503'); },
  });
  sync.record('tasks', 30);
  await sync.flush();
  assert.equal(calls.length, 1);
  // random() = 0.5 -> wait 15 s after the first failure.
  time += 14_999;
  await sync.flush();
  assert.equal(calls.length, 1, 'still waiting');
  time += 1;
  await sync.flush();
  assert.equal(calls.length, 2);
  time += 29_999; // second failure: up to 60 s -> 30 s
  await sync.flush();
  assert.equal(calls.length, 2);
  fail = false;
  await sync.flush({ force: true });
  assert.equal(calls.length, 3, 'back online / sign-out skips the wait');
  assert.deepEqual(sync.pending(), []);
  sync.record('tasks', 5);
  await sync.flush();
  assert.equal(calls.length, 4, 'a success clears the backoff');
});
