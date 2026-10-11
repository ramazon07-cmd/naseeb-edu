import test from 'node:test';
import assert from 'node:assert/strict';
import { RATE_LIMIT_WAIT_CAP, backoffCeiling, backoffDelay, busyRetryDelay, fullJitter, requestRetryDelay, retryAfterMs } from '../src/lib/backoff.js';

test('ceilings grow exponentially up to the cap', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map((attempt) => backoffCeiling(attempt, { base: 1000, cap: 30000 })), [1000, 2000, 4000, 8000, 16000, 30000, 30000]);
});

test('full jitter is uniform in [0, ceiling)', () => {
  assert.equal(fullJitter(1000, () => 0), 0);
  assert.equal(fullJitter(1000, () => 0.5), 500);
  assert.equal(fullJitter(1000, () => 0.9999), 999);
  let seen = new Set();
  for (let i = 0; i < 200; i += 1) {
    const delay = backoffDelay(3, { base: 1000, cap: 30000 });
    assert.ok(delay >= 0 && delay < 8000);
    seen.add(Math.floor(delay / 1000));
  }
  assert.ok(seen.size > 4, 'delays are spread out, not synchronized');
});

test('GET retries: transient statuses only, bounded, Retry-After respected', () => {
  const half = () => 0.5;
  assert.equal(requestRetryDelay(0, 0, null, undefined, half), 250);
  assert.equal(requestRetryDelay(1, 503, null, undefined, half), 500);
  assert.equal(requestRetryDelay(2, 503, null, undefined, half), null, 'two retries at most');
  for (const status of [400, 401, 403, 404, 408, 409, 413, 500]) assert.equal(requestRetryDelay(0, status, null, undefined, half), null, `no retry for ${status}`);
  assert.equal(requestRetryDelay(0, 429, '2', undefined, half), 2000);
  assert.equal(requestRetryDelay(0, 503, '120', undefined, half), null, 'a long pause is left to the caller');
  assert.equal(requestRetryDelay(0, 503, null, { retries: 0 }, half), null);
  assert.equal(retryAfterMs(new Date(Date.now() + 3000).toUTCString()) > 1000, true);
  assert.equal(retryAfterMs('soon'), null);
});

test('a 429 is retried only when Retry-After fits the cap', () => {
  const half = () => 0.5;
  assert.equal(requestRetryDelay(0, 429, '3', undefined, half), 3000);
  assert.equal(requestRetryDelay(0, 429, String(RATE_LIMIT_WAIT_CAP / 1000), undefined, half), RATE_LIMIT_WAIT_CAP);
  assert.equal(requestRetryDelay(0, 429, '9', undefined, half), null, 'longer than the cap: fail at once');
  assert.equal(requestRetryDelay(0, 429, '900', undefined, half), null, 'a lockout is never re-sent');
  assert.equal(requestRetryDelay(0, 429, null, undefined, half), 250, 'no Retry-After: jittered backoff');
  assert.equal(requestRetryDelay(2, 429, '1', undefined, half), null, 'two retries at most');
  assert.equal(requestRetryDelay(0, 429, '1', { retries: 0 }, half), null, 'writes (retries 0) are never retried');
});

test('busy retry: only rate limits, at least Retry-After, bounded', () => {
  const zero = () => 0;
  assert.equal(busyRetryDelay(0, { status: 500 }, undefined, zero), null, 'other failures show their error');
  assert.equal(busyRetryDelay(0, { status: 0 }, undefined, zero), null);
  assert.equal(busyRetryDelay(0, null, undefined, zero), null);
  assert.equal(busyRetryDelay(0, { status: 429 }, undefined, zero), 5000);
  assert.equal(busyRetryDelay(0, { status: 429, retryAfter: 12000 }, undefined, zero), 12000);
  assert.equal(busyRetryDelay(0, { status: 429, retryAfter: 600000 }, undefined, zero), null, 'a long wait shows the error');
  assert.equal(busyRetryDelay(3, { status: 429 }, undefined, zero), null, 'a section gives up after three tries');
  const signIn = { retries: Infinity, maxWait: Infinity };
  assert.equal(busyRetryDelay(50, { status: 429 }, signIn, () => 0.99), 30000, 'sign-in keeps trying, backoff capped');
  assert.equal(busyRetryDelay(50, { status: 429, retryAfter: 90000 }, signIn, zero), 90000, 'and waits the whole Retry-After');
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const delay = busyRetryDelay(attempt, { status: 429 });
    assert.ok(delay >= 5000 && delay <= 30000);
  }
});
