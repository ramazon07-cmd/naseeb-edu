import test from 'node:test';
import assert from 'node:assert/strict';
import { backoffCeiling, backoffDelay, fullJitter, requestRetryDelay, retryAfterMs } from '../src/lib/backoff.js';

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
  assert.equal(requestRetryDelay(0, 429, '120', undefined, half), null, 'a long pause is left to the caller');
  assert.equal(requestRetryDelay(0, 503, null, { retries: 0 }, half), null);
  assert.equal(retryAfterMs(new Date(Date.now() + 3000).toUTCString()) > 1000, true);
  assert.equal(retryAfterMs('soon'), null);
});
