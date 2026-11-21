import test from 'node:test';
import assert from 'node:assert/strict';
import { closeWindow, createLinkWatch, navigateWindow, openBlankWindow } from '../src/lib/telegramLink.js';

const flush = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };

// Fake clock and visibility: timers fire only when advance() reaches them.
function clock() {
  let time = 0;
  let hidden = false;
  let listener = null;
  let nextId = 1;
  const timers = new Map();
  return {
    options: {
      now: () => time,
      setTimer: (fn, ms) => { const id = nextId++; timers.set(id, { at: time + ms, fn }); return id; },
      clearTimer: (id) => timers.delete(id),
      isHidden: () => hidden,
      onVisibilityChange: (fn) => { listener = fn; return () => { listener = null; }; },
    },
    timers,
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
  };
}

function watch(statuses, { ttlMs = 900_000 } = {}) {
  const c = clock();
  const log = { checks: 0, linked: [], expired: 0 };
  const w = createLinkWatch({
    check: async () => { log.checks += 1; const next = statuses.length > 1 ? statuses.shift() : statuses[0]; if (next instanceof Error) throw next; return next; },
    onLinked: (status) => log.linked.push(status),
    onExpired: () => { log.expired += 1; },
    ttlMs,
    ...c.options,
  });
  return { c, log, w };
}

test('polls every 3 seconds and reports the link once, then stops', async () => {
  const { c, log, w } = watch([{ linked: false }, { linked: false }, { linked: true, enabled: true }]);
  w.start();
  await c.advance(2999);
  assert.equal(log.checks, 0);
  await c.advance(1);
  assert.equal(log.checks, 1);
  await c.advance(6000);
  assert.equal(log.checks, 3);
  assert.deepEqual(log.linked, [{ linked: true, enabled: true }]);
  assert.equal(w.isActive(), false);
  await c.advance(60_000);
  assert.equal(log.checks, 3, 'no more requests after success');
  assert.equal(log.expired, 0);
  assert.equal(c.timers.size, 0);
});

test('expires after the token lifetime and stops polling', async () => {
  const { c, log, w } = watch([{ linked: false }], { ttlMs: 15 * 60_000 });
  w.start();
  await c.advance(15 * 60_000 - 1);
  const before = log.checks;
  assert.ok(before >= 290);
  assert.equal(log.expired, 0);
  await c.advance(1);
  assert.equal(log.expired, 1);
  await c.advance(60_000);
  assert.equal(log.checks, before, 'nothing is requested after expiry');
  assert.equal(w.isActive(), false);
  assert.equal(c.timers.size, 0);
});

test('stop() (unmount, Later) ends everything, and a late answer is ignored', async () => {
  const c = clock();
  let release;
  const log = { linked: 0, expired: 0 };
  const w = createLinkWatch({
    check: () => new Promise((resolve) => { release = () => resolve({ linked: true }); }),
    onLinked: () => { log.linked += 1; },
    onExpired: () => { log.expired += 1; },
    ttlMs: 60_000,
    ...c.options,
  });
  w.start();
  await c.advance(3000);
  w.stop();
  release();
  await flush();
  assert.equal(log.linked, 0);
  assert.equal(c.timers.size, 0);
  await c.advance(120_000);
  assert.equal(log.expired, 0);
});

test('a hidden tab makes no requests', async () => {
  const { c, log, w } = watch([{ linked: false }]);
  w.start();
  await c.setHidden(true);
  await c.advance(60_000);
  assert.equal(log.checks, 0);
  await c.setHidden(false);
  assert.equal(log.checks, 1, 'checked right away when the tab is back');
  w.stop();
});

test('a failing status request is retried, not fatal', async () => {
  const { c, log, w } = watch([new Error('offline'), { linked: true }]);
  w.start();
  await c.advance(60_000);
  assert.equal(log.linked.length, 1);
  w.stop();
});

test('start() twice does not double the polling', async () => {
  const { c, log, w } = watch([{ linked: false }]);
  w.start();
  w.start();
  await c.advance(9000);
  assert.equal(log.checks, 3);
  w.stop();
});

test('the blank window is opened for the click and pointed at the link afterwards', () => {
  const win = { closed: false, location: { href: '' }, opener: 'page' };
  const opened = [];
  const got = openBlankWindow((...args) => { opened.push(args); return win; });
  assert.equal(got, win);
  assert.deepEqual(opened, [['', '_blank']]);
  assert.equal(win.opener, null);
  assert.equal(navigateWindow(win, 'https://t.me/bot?start=s_x'), true);
  assert.equal(win.location.href, 'https://t.me/bot?start=s_x');
});

test('a blocked or closed window falls back to the plain link', () => {
  assert.equal(openBlankWindow(() => null), null);
  assert.equal(openBlankWindow(() => { throw new Error('blocked'); }), null);
  assert.equal(openBlankWindow(() => ({ closed: true })), null);
  assert.equal(navigateWindow(null, 'https://t.me/x'), false);
  assert.equal(navigateWindow({ closed: true, location: {} }, 'https://t.me/x'), false);
  assert.equal(navigateWindow({ closed: false, get location() { throw new Error('gone'); } }, 'https://t.me/x'), false);
});

test('closeWindow only closes an open window and never throws', () => {
  const win = { closed: false, close() { this.closed = true; } };
  closeWindow(win);
  assert.equal(win.closed, true);
  closeWindow(null);
  closeWindow({ closed: false, close() { throw new Error('x'); } });
});
