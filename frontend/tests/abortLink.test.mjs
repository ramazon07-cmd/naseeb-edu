import test from 'node:test';
import assert from 'node:assert/strict';
import { linkAbort, readTextStream } from '../src/lib/abortLink.js';

function manualTimers() {
  const pending = new Map();
  let next = 1;
  return {
    setTimeout: (fn) => { const id = next++; pending.set(id, fn); return id; },
    clearTimeout: (id) => { pending.delete(id); },
    fire: () => { for (const fn of [...pending.values()]) fn(); pending.clear(); },
    pending,
  };
}

// A body that sends one chunk and then waits forever, like a slow AI stream.
function hangingBody() {
  let cancelled = false;
  const body = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('Hello ')); },
    cancel() { cancelled = true; },
  });
  return { body, cancelled: () => cancelled };
}

test('a stream keeps the caller abort linked after the headers arrive', () => {
  const caller = new AbortController();
  const timers = manualTimers();
  const link = linkAbort(caller.signal, 45_000, timers);
  link.release(); // headers arrived
  assert.equal(timers.pending.size, 0, 'the header timeout is cleared');
  caller.abort(); // Stop pressed while streaming
  assert.equal(link.signal.aborted, true);
  assert.equal(link.timedOut(), false);
});

test('a plain request drops the caller link once it is done', () => {
  const caller = new AbortController();
  const link = linkAbort(caller.signal, 15_000, manualTimers());
  link.unlink();
  caller.abort();
  assert.equal(link.signal.aborted, false);
});

test('the header timeout aborts and is reported as a timeout', () => {
  const timers = manualTimers();
  const link = linkAbort(undefined, 45_000, timers);
  timers.fire();
  assert.equal(link.signal.aborted, true);
  assert.equal(link.timedOut(), true);
});

test('an already aborted caller aborts at once', () => {
  const caller = new AbortController();
  caller.abort();
  assert.equal(linkAbort(caller.signal, 1000, manualTimers()).signal.aborted, true);
});

test('aborting after headers stops reader.read() and cancels the body', async () => {
  const controller = new AbortController();
  const { body, cancelled } = hangingBody();
  const seen = [];
  const reading = readTextStream(body, controller.signal, (text) => {
    seen.push(text);
    setTimeout(() => controller.abort(), 0);
  });
  await assert.rejects(reading, { name: 'AbortError' });
  assert.deepEqual(seen, ['Hello ']);
  assert.equal(cancelled(), true);
});

test('a finished stream returns the whole text', async () => {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('Hi '));
      controller.enqueue(new TextEncoder().encode('there'));
      controller.close();
    },
  });
  const updates = [];
  assert.equal(await readTextStream(body, new AbortController().signal, (text) => updates.push(text)), 'Hi there');
  assert.deepEqual(updates, ['Hi ', 'Hi there']);
});
