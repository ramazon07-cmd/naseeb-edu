import test from 'node:test';
import assert from 'node:assert/strict';
import { isPastDay, pickRangeDay, isRangeBetween, isRangeStart, isRangeEnd, rangeText, windowFromApi, windowToApi, windowProblem } from '../src/lib/dateRange.js';
import { cancelledByStudent, weekCounts, bookedPerDay } from '../src/lib/meetings.js';

const today = '2026-11-15';

test('range summary text: same year, across years, one day, empty', () => {
  assert.equal(rangeText('2026-11-16', '2026-11-22'), '16 Nov – 22 Nov 2026');
  assert.equal(rangeText('2026-12-28', '2027-01-03'), '28 Dec 2026 – 3 Jan 2027');
  assert.equal(rangeText('2026-11-16', '2026-11-16'), '16 Nov 2026');
  assert.equal(rangeText('2026-11-16', null), '16 Nov 2026');
  assert.equal(rangeText(null, null), '');
});

test('past days are disabled, today is not', () => {
  assert.equal(isPastDay('2026-11-14', today), true);
  assert.equal(isPastDay('2026-11-15', today), false);
  assert.deepEqual(pickRangeDay({ start: null, end: null }, '2026-11-14', today), { start: null, end: null });
});

test('first click starts, second ends, earlier second click restarts, a third click starts over', () => {
  let range = { start: null, end: null };
  range = pickRangeDay(range, '2026-11-20', today);
  assert.deepEqual(range, { start: '2026-11-20', end: null });
  range = pickRangeDay(range, '2026-11-18', today); // earlier: new start
  assert.deepEqual(range, { start: '2026-11-18', end: null });
  range = pickRangeDay(range, '2026-11-25', today);
  assert.deepEqual(range, { start: '2026-11-18', end: '2026-11-25' });
  range = pickRangeDay(range, '2026-12-01', today); // complete range: start again
  assert.deepEqual(range, { start: '2026-12-01', end: null });
  assert.deepEqual(pickRangeDay({ start: '2026-11-20', end: null }, '2026-11-20', today), { start: '2026-11-20', end: '2026-11-20' });
});

test('days between are shaded, the ends are their own', () => {
  const range = { start: '2026-11-16', end: '2026-11-22' };
  assert.equal(isRangeBetween('2026-11-19', range), true);
  assert.equal(isRangeBetween('2026-11-16', range), false);
  assert.equal(isRangeBetween('2026-11-22', range), false);
  assert.equal(isRangeStart('2026-11-16', range), true);
  assert.equal(isRangeEnd('2026-11-22', range), true);
  assert.equal(isRangeBetween('2026-11-19', { start: '2026-11-16', end: null }), false);
});

test('window: API defaults, payload and validation', () => {
  assert.deepEqual(windowFromApi({}), { mode: 'rolling', days: '60', start: null, end: null });
  assert.deepEqual(windowFromApi({ window_mode: 'range', window_days: 60, window_start: '2026-11-16', window_end: '2026-11-22' }), { mode: 'range', days: '60', start: '2026-11-16', end: '2026-11-22' });
  assert.deepEqual(windowToApi({ mode: 'rolling', days: '30', start: '2026-11-16', end: null }), { window_mode: 'rolling', window_days: 30, window_start: null, window_end: null });
  assert.deepEqual(windowToApi({ mode: 'range', days: '60', start: '2026-11-16', end: null }), { window_mode: 'range', window_days: 60, window_start: '2026-11-16', window_end: '2026-11-16' });
  assert.equal(windowProblem({ mode: 'rolling', days: '60' }, today), '');
  for (const days of ['', '0', '366', '1.5', 'x']) assert.equal(windowProblem({ mode: 'rolling', days }, today), 'days');
  assert.equal(windowProblem({ mode: 'range', start: null, end: null }, today), 'range_missing');
  assert.equal(windowProblem({ mode: 'range', start: '2026-11-20', end: '2026-11-18' }, today), 'range_order');
  assert.equal(windowProblem({ mode: 'range', start: '2026-11-01', end: '2026-11-10' }, today), 'range_past');
  assert.equal(windowProblem({ mode: 'range', start: '2026-11-16', end: '2026-11-22' }, today), '');
});

test('counselor week: counts, per-day counts and who cancelled', () => {
  const items = [
    { status: 'approved', starts_at: '2026-11-16T09:00:00Z', student: 1 },
    { status: 'pending', starts_at: '2026-11-16T11:00:00Z', student: 2 },
    { status: 'cancelled', starts_at: '2026-11-17T09:00:00Z', student: 3, cancelled_by: 3 },
    { status: 'cancelled', starts_at: '2026-11-17T10:00:00Z', student: 4, cancelled_by_role: 'counselor' },
    { status: 'completed', starts_at: '2026-11-18T09:00:00Z', student: 5 },
  ];
  assert.deepEqual(weekCounts(items), { booked: 3, cancelled: 2 });
  assert.deepEqual(bookedPerDay(items), [['2026-11-16', 2], ['2026-11-18', 1]]);
  assert.equal(cancelledByStudent(items[2]), true);
  assert.equal(cancelledByStudent(items[3]), false);
  assert.equal(cancelledByStudent({ status: 'cancelled', cancelled_by_role: 'student' }), true);
  assert.equal(cancelledByStudent({ status: 'approved', cancelled_by_role: 'student' }), false);
});
