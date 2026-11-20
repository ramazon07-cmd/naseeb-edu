import test from 'node:test';
import assert from 'node:assert/strict';
import { averageSide, averageText } from '../src/lib/screenTimeAverage.js';

const fmt = (seconds) => `${Math.floor(seconds / 60)} min`;
const week = (...minutes) => minutes.map((m) => ({ seconds: m * 60 }));

test('an average under a minute never reads as 0', () => {
  assert.equal(averageText(34, fmt, 'min'), '< 1 min');
  assert.equal(averageText(0, fmt, 'min'), '0 min');
  assert.equal(averageText(300, fmt, 'min'), '5 min');
});

test('the label moves to the start when a bar at the end rises above the line', () => {
  // The reported case: 4 minutes on Friday, nothing else, so the average is about 34 s.
  const rows = week(0, 0, 0, 0, 0, 4, 0);
  assert.equal(averageSide(rows, 240 / 7), 'start');
});

test('the label stays at the end when the end is clear or both ends are busy', () => {
  assert.equal(averageSide(week(9, 0, 0, 0, 0, 0, 0), 540 / 7), 'end');
  assert.equal(averageSide(week(9, 9, 1, 1, 1, 9, 9), 39 * 60 / 7), 'end');
});
