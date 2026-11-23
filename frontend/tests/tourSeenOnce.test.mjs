import test from 'node:test';
import assert from 'node:assert/strict';

function memoryStorage() {
  const map = new Map();
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k) };
}
globalThis.localStorage = memoryStorage();
const { siteTourSeen, markSiteTourSeen } = await import('../src/design/blue/tourSeen.js');
const { pageTipsSeen, markPageTipsSeen } = await import('../src/design/blue/pageTips.js');

test('site tour is remembered per account and never replays', () => {
  assert.equal(siteTourSeen(1), false);
  markSiteTourSeen(1);
  assert.equal(siteTourSeen(1), true);
  assert.equal(siteTourSeen(2), false);
});

test('page tips are remembered per user and per page', () => {
  assert.equal(pageTipsSeen(7, 'tasks'), false);
  markPageTipsSeen(7, 'tasks');
  assert.equal(pageTipsSeen(7, 'tasks'), true);
  assert.equal(pageTipsSeen(7, 'messages'), false);
  assert.equal(pageTipsSeen(8, 'tasks'), false);
  markPageTipsSeen(7, 'messages');
  assert.equal(pageTipsSeen(7, 'tasks'), true);
});

test('page tips stay seen when storage refuses writes', () => {
  const saved = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() {} };
  markPageTipsSeen(9, 'tasks');
  markSiteTourSeen(9);
  assert.equal(pageTipsSeen(9, 'tasks'), true);
  assert.equal(siteTourSeen(9), true);
  globalThis.localStorage = saved;
});
