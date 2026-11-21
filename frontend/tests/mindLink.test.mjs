import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isCodeExpired, latestComparable, majorOffer, mindCardState, mismatchedAttempts, shouldCheckOnFocus, startMindLink,
} from '../src/lib/mindLink.js';

test('the card is hidden when the feature is off or the status is unknown', () => {
  assert.equal(mindCardState(null), 'hidden');
  assert.equal(mindCardState({ available: false, linked: false }), 'hidden');
  assert.equal(mindCardState({ available: false, linked: true }), 'hidden');
});

test('card states: start, waiting for the student to come back, linked', () => {
  assert.equal(mindCardState({ available: true, linked: false }), 'idle');
  assert.equal(mindCardState({ available: true, linked: false }, { waiting: true }), 'waiting');
  assert.equal(mindCardState({ available: true, linked: true }, { waiting: true }), 'linked');
});

test('starting opens the tab before the request and sends it to the Naseeb Mind url', async () => {
  const calls = [];
  const win = { id: 'tab' };
  const result = await startMindLink({
    lang: 'ru',
    start: async (lang) => { calls.push(['start', lang]); return { url: 'https://naseebmind.uz/connect?code=x' }; },
    open: () => { calls.push(['open']); return win; },
    navigate: (target, url) => { calls.push(['navigate', target, url]); return true; },
    close: () => calls.push(['close']),
  });
  assert.deepEqual(calls.map((call) => call[0]), ['open', 'start', 'navigate']);
  assert.deepEqual(result, { url: 'https://naseebmind.uz/connect?code=x', expiresAt: undefined, opened: true });
});

test('a blocked tab still returns the url, and a failed start closes the blank tab', async () => {
  const blocked = await startMindLink({
    lang: 'uz', start: async () => ({ url: 'u' }), open: () => null, navigate: () => false, close() {},
  });
  assert.deepEqual(blocked, { url: 'u', expiresAt: undefined, opened: false });
  let closed = 0;
  await assert.rejects(startMindLink({
    lang: 'uz', start: async () => { throw new Error('nope'); }, open: () => ({}), navigate: () => true, close: () => { closed += 1; },
  }), /nope/);
  assert.equal(closed, 1);
});

test('returning to the tab re-checks only while waiting, and not in a burst', () => {
  assert.equal(shouldCheckOnFocus({ waiting: false, lastCheckAt: 0, now: 100000 }), false);
  assert.equal(shouldCheckOnFocus({ waiting: true, lastCheckAt: 0, now: 100000 }), true);
  assert.equal(shouldCheckOnFocus({ waiting: true, lastCheckAt: 99000, now: 100000 }), false);
});

test('mismatched-version attempts are marked and never the current result', () => {
  const rows = [
    { id: 3, challenge: 'personality', source_version_mismatch: true },
    { id: 2, challenge: 'personality', source_version_mismatch: false },
    { id: 1, challenge: 'interests' },
  ];
  assert.deepEqual(latestComparable(rows), { personality: rows[1], interests: rows[2] });
  assert.deepEqual(mismatchedAttempts(rows), [rows[0]]);
  assert.deepEqual(latestComparable([rows[0]]), {});
});

test('the Naseeb Mind major is offered only to a student without one', () => {
  const status = { chosen_major: ' Biology ' };
  assert.equal(majorOffer(status, { target_major: '' }), 'Biology');
  assert.equal(majorOffer(status, { target_major: 'Law' }), '');
  assert.equal(majorOffer({ chosen_major: null }, { target_major: '' }), '');
  assert.equal(majorOffer(status, undefined), '');
});

test('an expired code returns the waiting card to a restart, never stays waiting', () => {
  const status = { available: true, linked: false };
  assert.equal(mindCardState(status, { waiting: true, expired: true }), 'expired');
  assert.equal(mindCardState(status, { waiting: false, expired: true }), 'idle');
  assert.equal(mindCardState({ available: true, linked: true }, { waiting: true, expired: true }), 'linked');
  const at = '2026-11-21T10:10:00Z';
  const t0 = new Date(at).getTime();
  assert.equal(isCodeExpired(at, t0 - 1), false);
  assert.equal(isCodeExpired(at, t0), true);
  assert.equal(isCodeExpired(undefined, t0), false);
  assert.equal(isCodeExpired('garbage', t0), false);
});

test('starting also returns expires_at so the card can time the code out', async () => {
  const result = await startMindLink({
    lang: 'en', start: async () => ({ url: 'u', expires_at: '2026-11-21T10:10:00Z' }), open: () => null, navigate: () => false, close() {},
  });
  assert.deepEqual(result, { url: 'u', expiresAt: '2026-11-21T10:10:00Z', opened: false });
});
