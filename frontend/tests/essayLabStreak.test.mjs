import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildMonth, canGoNext, dayState, daysInMonth, firstWeekday, isValidStreak, latestEdit, monthOf, progressPercent,
  shiftMonth,
} from '../src/essayLab/streakModel.js';

test('months shift across year boundaries', () => {
  assert.equal(shiftMonth('2026-01', -1), '2025-12');
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2026-11', -11), '2025-12');
  assert.equal(shiftMonth('2026-11', 0), '2026-11');
});

test('next month is only allowed before the server month', () => {
  assert.equal(canGoNext('2026-10', '2026-11-08'), true);
  assert.equal(canGoNext('2026-11', '2026-11-08'), false);
  assert.equal(canGoNext('2026-12', '2026-11-08'), false);
  assert.equal(monthOf('2026-11-08'), '2026-11');
});

test('month length and Monday-first offset', () => {
  assert.equal(daysInMonth('2026-02'), 28);
  assert.equal(daysInMonth('2028-02'), 29);
  assert.equal(daysInMonth('2026-11'), 30);
  assert.equal(firstWeekday('2026-11'), 6); // 1 Nov 2026 is a Sunday
  assert.equal(firstWeekday('2026-06'), 0); // 1 Jun 2026 is a Monday
});

test('day states: fire, ember, none and future', () => {
  const days = { '2026-11-06': 'fire', '2026-11-07': 'ember', '2026-11-20': 'fire' };
  assert.equal(dayState('2026-11-06', days, '2026-11-08'), 'fire');
  assert.equal(dayState('2026-11-07', days, '2026-11-08'), 'ember');
  assert.equal(dayState('2026-11-05', days, '2026-11-08'), 'none');
  assert.equal(dayState('2026-11-08', days, '2026-11-08'), 'none');
  assert.equal(dayState('2026-11-09', days, '2026-11-08'), 'future');
  assert.equal(dayState('2026-11-20', days, '2026-11-08'), 'future');
  assert.equal(dayState('2026-11-05', undefined, '2026-11-08'), 'none');
  assert.equal(dayState('2026-11-05', { '2026-11-05': 'bogus' }, '2026-11-08'), 'none');
});

test('the calendar is whole weeks starting on Monday and marks today', () => {
  const weeks = buildMonth('2026-11', { '2026-11-08': 'fire', '2026-11-03': 'ember' }, '2026-11-08');
  assert.ok(weeks.every((week) => week.length === 7));
  assert.equal(weeks.length, 6);
  assert.deepEqual(weeks[0].map((cell) => cell?.day ?? null), [null, null, null, null, null, null, 1]);
  assert.deepEqual(weeks[5].map((cell) => cell?.day ?? null), [30, null, null, null, null, null, null]);
  const flat = weeks.flat().filter(Boolean);
  assert.equal(flat.length, 30);
  assert.deepEqual(flat.filter((cell) => cell.isToday).map((cell) => cell.key), ['2026-11-08']);
  assert.equal(flat.find((cell) => cell.day === 8).state, 'fire');
  assert.equal(flat.find((cell) => cell.day === 3).state, 'ember');
  assert.equal(flat.find((cell) => cell.day === 9).state, 'future');
  assert.equal(flat.find((cell) => cell.day === 4).state, 'none');
});

test('a past month has no future days and no today', () => {
  const flat = buildMonth('2026-10', {}, '2026-11-08').flat().filter(Boolean);
  assert.equal(flat.length, 31);
  assert.ok(flat.every((cell) => cell.state === 'none' && !cell.isToday));
});

test('progress follows whichever goal is closer and stays within 0-100', () => {
  const goal = { words: 100, minutes: 10 };
  assert.equal(progressPercent({ words: 0, minutes: 0 }, goal), 0);
  assert.equal(progressPercent({ words: 40, minutes: 2 }, goal), 40);
  assert.equal(progressPercent({ words: 10, minutes: 5 }, goal), 50);
  const served = { words: 100, minutes: 10, min_words: 25 };
  assert.equal(progressPercent({ words: 10, minutes: 5 }, served), 40);
  assert.equal(progressPercent({ words: 0, minutes: 10 }, served), 0);
  assert.equal(progressPercent({ words: 25, minutes: 10 }, served), 100);
  assert.equal(progressPercent({ words: 142, minutes: 0 }, goal), 100);
  assert.equal(progressPercent({ words: -5, minutes: 0 }, goal), 0);
  assert.equal(progressPercent(null, goal), 0);
  assert.equal(progressPercent({ words: 5 }, null), 0);
});

test('the newest edit time changes when a save lands', () => {
  assert.equal(latestEdit([]), '');
  assert.equal(latestEdit(null), '');
  const before = [{ last_edited_at: '2026-11-08T04:00:00Z' }, { updated_at: '2026-11-07T04:00:00Z' }];
  const after = [{ last_edited_at: '2026-11-08T04:05:00Z' }, { updated_at: '2026-11-07T04:00:00Z' }];
  assert.equal(latestEdit(before), '2026-11-08T04:00:00Z');
  assert.notEqual(latestEdit(before), latestEdit(after));
});

test('only a complete streak answer is accepted', () => {
  const good = { today: '2026-11-08', current: 3, best: 5, month: '2026-11', progress: { words: 1, minutes: 0, goal_met: false }, goal: { words: 100, minutes: 10 }, days: {} };
  assert.equal(isValidStreak(good), true);
  assert.equal(isValidStreak(null), false);
  assert.equal(isValidStreak({ ...good, current: undefined }), false);
  assert.equal(isValidStreak({ ...good, goal: null }), false);
  assert.equal(isValidStreak([]), false);
});
