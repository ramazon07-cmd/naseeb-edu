import test from 'node:test';
import assert from 'node:assert/strict';
import { MESSAGE_POLL, nextPollDelay } from '../src/lib/pollDelay.js';

test('quiet conversations are polled less and less often, up to the maximum', () => {
  const delays = [MESSAGE_POLL.min];
  for (let index = 0; index < 6; index += 1) delays.push(nextPollDelay(delays.at(-1), false));
  assert.deepEqual(delays, [8000, 12000, 18000, 27000, 30000, 30000, 30000]);
});

test('a change goes straight back to the fastest poll', () => {
  assert.equal(nextPollDelay(30000, true), MESSAGE_POLL.min);
  assert.equal(nextPollDelay(MESSAGE_POLL.min, true), MESSAGE_POLL.min);
});
