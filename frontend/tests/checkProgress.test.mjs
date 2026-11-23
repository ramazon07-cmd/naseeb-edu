import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CAP, DEFAULT_EXPECTED_MS, HISTORY_KEY, MAX_EXPECTED_MS, MIN_EXPECTED_MS, STAGES,
  expectedDuration, expectedFromHistory, progressFraction, readDurations, recordDuration, secondsLeft, stageIndex,
} from '../src/lib/checkProgress.js';

const memory = (initial) => {
  const data = new Map(initial ? [[HISTORY_KEY, initial]] : []);
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v) };
};

test('progress starts at zero, rises, and never reaches the cap or 100%', () => {
  assert.equal(progressFraction(0), 0);
  let last = 0;
  for (const ms of [1000, 5000, 20000, 45000, 90000, 600000]) {
    const value = progressFraction(ms);
    assert.ok(value > last && value < CAP + 1e-9 && value < 1, `at ${ms}`);
    last = value;
  }
  assert.ok(progressFraction(45000) > 0.75, 'close to the cap at the expected time');
});

test('progress tolerates bad input', () => {
  assert.equal(progressFraction(-5), 0);
  assert.equal(progressFraction(NaN), 0);
  assert.ok(progressFraction(1000, 0) > 0);
});

test('stages advance with elapsed time', () => {
  assert.deepEqual([0, 10000, 25000, 40000, 200000].map((ms) => stageIndex(ms)), [0, 1, 2, 3, 3]);
  assert.equal(STAGES[0].label, 'Reading your essay');
});

test('time left rounds up to 5s and ends with null', () => {
  assert.equal(secondsLeft(0), 45);
  assert.equal(secondsLeft(5000), 40);
  assert.equal(secondsLeft(7000), 40);
  assert.equal(secondsLeft(43000), null);
  assert.equal(secondsLeft(120000), null);
});

test('expected duration averages recent checks within sane bounds', () => {
  assert.equal(expectedFromHistory([]), DEFAULT_EXPECTED_MS);
  assert.equal(expectedFromHistory([30000, 50000]), 40000);
  assert.equal(expectedFromHistory([1000]), MIN_EXPECTED_MS);
  assert.equal(expectedFromHistory([500000]), MAX_EXPECTED_MS);
  assert.equal(expectedFromHistory(['x', null, -3]), DEFAULT_EXPECTED_MS);
});

test('history is stored, trimmed to five, and ignores instant results', () => {
  const store = memory();
  recordDuration(500, store);
  assert.deepEqual(readDurations(store), []);
  [20000, 30000, 40000, 50000, 60000, 70000].forEach((ms) => recordDuration(ms, store));
  assert.deepEqual(readDurations(store), [30000, 40000, 50000, 60000, 70000]);
  assert.equal(expectedDuration(store), 50000);
});

test('broken or unavailable storage falls back to the default', () => {
  assert.equal(expectedDuration(memory('not json')), DEFAULT_EXPECTED_MS);
  const throwing = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  assert.equal(expectedDuration(throwing), DEFAULT_EXPECTED_MS);
  assert.doesNotThrow(() => recordDuration(30000, throwing));
});
