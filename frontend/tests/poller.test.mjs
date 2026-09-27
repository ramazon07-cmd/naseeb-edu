import test from 'node:test';
import assert from 'node:assert/strict';
import { createPoller } from '../src/lib/poller.js';
import { MESSAGE_POLL, nextPollDelay } from '../src/lib/pollDelay.js';

const flush = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };

function harness({ results = [], random = () => 0.5, ...options } = {}) {
  let time = 0;
  let hidden = false;
  let listener = null;
  const timers = new Map();
  let nextId = 1;
  const runs = [];
  const poller = createPoller({
    run: async () => { runs.push(time); const result = results.length ? results.shift() : false; if (result instanceof Error) throw result; return result; },
    min: MESSAGE_POLL.min, max: MESSAGE_POLL.max, nextDelay: nextPollDelay, random,
    now: () => time,
    setTimer: (fn, ms) => { const id = nextId++; timers.set(id, { at: time + ms, fn }); return id; },
    clearTimer: (id) => timers.delete(id),
    isHidden: () => hidden,
    onVisibilityChange: (fn) => { listener = fn; return () => { listener = null; }; },
    ...options,
  });
  return {
    poller, runs, timers,
    async advance(ms) {
      const end = time + ms;
      await flush();
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        time = due[1].at;
        due[1].fn();
        await flush();
      }
      time = end;
      await flush();
    },
    async setHidden(value) { hidden = value; listener?.(); await flush(); },
    listening: () => listener !== null,
  };
}

test('polls at the idle cadence and speeds up after a change', async () => {
  const h = harness({ results: [false, false, true, false] });
  h.poller.start();
  await h.advance(8000 + 12000 + 18000 + 8000);
  assert.deepEqual(h.runs, [8000, 20000, 38000, 46000]);
  h.poller.stop();
});

test('a hidden tab makes no requests and keeps no timers; showing it refreshes at once', async () => {
  const h = harness();
  h.poller.start();
  await h.setHidden(true);
  assert.equal(h.timers.size, 0);
  await h.advance(10 * 60000);
  assert.equal(h.runs.length, 0);
  await h.setHidden(false);
  assert.equal(h.runs.length, 1, 'immediate refresh on visibilitychange');
  await h.advance(11999);
  assert.equal(h.runs.length, 1);
  await h.advance(1);
  assert.equal(h.runs.length, 2, 'then the normal cadence, restarted from the fastest step');
  h.poller.stop();
  assert.equal(h.listening(), false);
  assert.equal(h.timers.size, 0);
});

test('failures back off exponentially with full jitter', async () => {
  const error = new Error('down');
  const h = harness({ results: [error, error, error, null, true], random: () => 0.5 });
  h.poller.start({ immediate: true });
  await h.advance(4000 + 8000 + 15000 + 15000);
  // random() = 0.5 -> half of 8 s, 16 s, 30 s (cap), 30 s.
  assert.deepEqual(h.runs, [0, 4000, 12000, 27000, 42000]);
  assert.equal(h.poller.getState().failures, 0);
});

test('failed polls never retry faster than min / 8', async () => {
  const h = harness({ results: [new Error('x'), false], random: () => 0 });
  h.poller.start({ immediate: true });
  await h.advance(999);
  assert.equal(h.runs.length, 1);
  await h.advance(1);
  assert.equal(h.runs.length, 2);
});

test('poke runs now (once, even while busy); reset only shortens the wait', async () => {
  let release;
  const h = harness({ run: () => new Promise((resolve) => { release = resolve; }) });
  h.poller.start();
  await h.advance(8000);
  h.poller.poke();
  h.poller.poke();
  release(false);
  await h.advance(0);
  assert.ok(h.poller.getState().busy, 'the queued poke ran right after');
  release(false);
  await h.advance(0);
  const k = harness({ results: [false, false, false] });
  k.poller.start({ immediate: true });
  await k.advance(8000 + 12000);
  k.poller.reset();
  await k.advance(8000);
  assert.equal(k.runs.length, 3);
});

test('quick tab flips reuse a fresh result instead of refreshing again', async () => {
  const h = harness();
  h.poller.start({ immediate: true });
  await h.advance(100);
  assert.deepEqual(h.runs, [0]);
  for (let i = 0; i < 5; i += 1) {
    await h.setHidden(true);
    await h.advance(300);
    await h.setHidden(false);
  }
  assert.deepEqual(h.runs, [0], 'no request per switch within revisitMin (min / 4 = 2 s)');
  assert.equal(h.timers.size, 1);
  // The cadence resumes from the last run, not from the last switch.
  await h.advance(8000 - 1600 - 1);
  assert.deepEqual(h.runs, [0]);
  await h.advance(1);
  assert.deepEqual(h.runs, [0, 8000]);
  h.poller.stop();
});

test('returning after revisitMin refreshes at once', async () => {
  const h = harness();
  h.poller.start({ immediate: true });
  await h.advance(100);
  await h.setHidden(true);
  await h.advance(1900);
  await h.setHidden(false);
  assert.deepEqual(h.runs, [0, 2000]);
  h.poller.stop();
});

test('revisitMin is configurable; failed runs never count as fresh', async () => {
  const h = harness({ results: [new Error('down')], revisitMin: 15000 });
  h.poller.start({ immediate: true });
  await h.advance(100);
  await h.setHidden(true);
  await h.setHidden(false);
  assert.deepEqual(h.runs, [0, 100], 'the last run failed, so refresh now');
  await h.setHidden(true);
  await h.advance(14000);
  await h.setHidden(false);
  assert.deepEqual(h.runs, [0, 100], 'still inside 15 s of the last success');
  h.poller.stop();
});

test('poke stays immediate right after a run', async () => {
  const h = harness();
  h.poller.start({ immediate: true });
  await h.advance(10);
  h.poller.poke();
  await h.advance(0);
  assert.deepEqual(h.runs, [0, 10]);
  h.poller.stop();
});
