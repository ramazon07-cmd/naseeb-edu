import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  DEFAULT_LAYOUT, HOME_CARDS, WIDE_CARDS, allClear, allSetSeen, heatLevel,
  heatmapWeeks, markAllSetSeen, snapshotChoices, bucketShares, checkInAction, checkedDays, greetingKey, homeReasons, loadLayout, moveCard,
  normalizeLayout, saveLayout, setCheckIn, toggleCard, visibleCards,
  addCheckedIn, checkInKey, checkInOutcome, checkInPage, mergeCheckInRows, setCheckInRow, withPending, todayMeetingsState,
} from '../src/lib/counselorHome.js';
import { approveReviewItem } from '../src/lib/reviewQueue.js';

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), values };
}

test('layouts keep known cards once, then add new cards where the default order puts them', () => {
  assert.deepEqual(normalizeLayout(null), { order: HOME_CARDS, hidden: [] });
  assert.deepEqual(normalizeLayout({ order: ['progress', 'nope', 'progress', 'review'], hidden: ['review', 'x'] }), {
    order: ['stats', 'progress', 'review', 'need_you', 'snapshot', 'today', 'deadlines', 'check_ins'],
    hidden: ['review'],
  });
  // A layout saved before "Student snapshot" existed.
  const saved = { order: ['stats', 'review', 'need_you', 'today', 'deadlines', 'check_ins', 'progress'], hidden: ['today'] };
  assert.deepEqual(normalizeLayout(saved), { order: HOME_CARDS, hidden: ['today'] });
  assert.deepEqual(normalizeLayout({ order: ['progress', 'stats'] }).order.slice(0, 3), ['progress', 'stats', 'review']);
  // A layout saved while "One thing needs you first" existed: that card is gone.
  assert.deepEqual(normalizeLayout({ order: ['first', 'stats', 'review'], hidden: ['first'] }), { order: HOME_CARDS, hidden: [] });
  assert.deepEqual(normalizeLayout('garbage'), normalizeLayout(DEFAULT_LAYOUT));
});

test('layouts are saved per account and survive broken storage', () => {
  const storage = memoryStorage();
  const layout = toggleCard(moveCard(normalizeLayout(null), 'progress', -1), 'today');
  assert.equal(saveLayout(storage, 7, layout), true);
  assert.deepEqual(loadLayout(storage, 7), layout);
  assert.deepEqual(loadLayout(storage, 8), normalizeLayout(null));
  storage.setItem('naseeb-counselor-home-v1:9', '{not json');
  assert.deepEqual(loadLayout(storage, 9), normalizeLayout(null));
  const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.deepEqual(loadLayout(throwing, 7), normalizeLayout(null));
  assert.equal(saveLayout(throwing, 7, layout), false);
  assert.deepEqual(loadLayout(() => { throw new Error('no storage'); }, 7), normalizeLayout(null));
});

test('moving and hiding cards', () => {
  const layout = normalizeLayout(null);
  assert.equal(moveCard(layout, HOME_CARDS[0], -1), layout);
  assert.deepEqual(moveCard(layout, 'review', 1).order.slice(0, 3), ['stats', 'need_you', 'review']);
  const hidden = toggleCard(layout, 'stats');
  assert.deepEqual(visibleCards(hidden), HOME_CARDS.filter((id) => id !== 'stats'));
  assert.deepEqual(WIDE_CARDS.filter((id) => !HOME_CARDS.includes(id)), []);
  assert.deepEqual(toggleCard(hidden, 'stats').hidden, []);
});

test('greeting by hour', () => {
  assert.equal(greetingKey(6), 'Good morning');
  assert.equal(greetingKey(12), 'Good afternoon');
  assert.equal(greetingKey(18), 'Good evening');
});

test('check-in days: activity days are fixed, future days closed', () => {
  const today = '2026-10-07';
  assert.equal(checkInAction(null, '2026-10-05', today), 'on');
  assert.equal(checkInAction('manual', today, today), 'off');
  assert.equal(checkInAction('auto', '2026-10-05', today), null);
  assert.equal(checkInAction(null, '2026-10-08', today), null);
  const checkIns = { checked_in: 1, students_total: 2, students: [
    { student: 1, days: ['auto', null, null, null, null, null, null] },
    { student: 2, days: [null, null, null, null, null, null, null] },
  ] };
  const on = setCheckIn(checkIns, 2, 1, true);
  assert.deepEqual(on.students[1].days.slice(0, 2), [null, 'manual']);
  assert.equal(on.checked_in, 2);
  assert.equal(checkedDays(on.students[1]), 1);
  assert.equal(setCheckIn(on, 2, 1, false).checked_in, 1);
  assert.equal(setCheckIn(checkIns, 1, 0, false).students[0].days[0], 'auto');
});

test('progress shares add up to 100', () => {
  assert.deepEqual(bucketShares({ on_track: 2, behind: 0, needs_attention: 1 }), { on_track: 67, behind: 0, needs_attention: 33 });
  assert.deepEqual(bucketShares({ on_track: 1, behind: 1, needs_attention: 1 }), { on_track: 34, behind: 33, needs_attention: 33 });
  assert.deepEqual(bucketShares({}), { on_track: 0, behind: 0, needs_attention: 0 });
});

test('server reasons read like the Students page reasons', () => {
  assert.deepEqual(homeReasons([{ key: 'late_task', count: 4 }, { key: 'missing_document', count: 1, title: 'IELTS' }]), [
    { key: 'late_task', count: 4, tone: 'danger', countPattern: '{n} late task|{n} late tasks' },
    { key: 'missing_document', count: 1, title: 'IELTS', tone: 'danger', countPattern: undefined },
  ]);
});

test('Home reads its lists from the server, not the first page of students (bug #7)', () => {
  const page = readFileSync(new URL('../src/pages/DashboardPage.jsx', import.meta.url), 'utf8');
  const home = page.slice(page.indexOf('function CounselorHome('), page.indexOf('export function StudentDashboard('));
  assert.match(home, /useCounselorHome\(stats, refreshStats\)/);
  assert.doesNotMatch(home, /usePagedList\('students'/);
});

test('Home and the badges share one ?include=home stats call (no second stats request)', () => {
  const page = readFileSync(new URL('../src/pages/DashboardPage.jsx', import.meta.url), 'utf8');
  const home = page.slice(page.indexOf('function useCounselorHome('), page.indexOf('export function StudentDashboard('));
  assert.doesNotMatch(home, /api\.counselorHome\(|api\.dashboard\(/);
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(app, /workspaceStatsRequest = [^\n]*routedPage\(activeUser\) === 'dashboard' \? api\.counselorHome\(\) : api\.dashboard\(\)/);
});

test('a check-in moves the total by its own row, even when the grid shows a capped page', () => {
  const checkIns = { students_total: 300, checked_in: 120, students: [
    { student: 1, days: ['auto', null, null, null, null, null, null] },
    { student: 2, days: [null, null, null, null, null, null, null] },
  ] };
  assert.equal(setCheckIn(checkIns, 2, 1, true).checked_in, 121);
  assert.equal(setCheckIn(checkIns, 1, 1, true).checked_in, 120);
  const back = setCheckIn(setCheckIn(checkIns, 2, 1, true), 2, 1, false);
  assert.equal(back.checked_in, 120);
  // The server's days replace the row as a whole.
  const server = setCheckIn(checkIns, 2, 1, true, ['auto', null, null, null, null, null, null]);
  assert.deepEqual(server.students[1].days[0], 'auto');
  assert.equal(server.students[1].days[1], null);
  const { rows, delta } = setCheckInRow(checkIns.students, 2, 0, true);
  assert.equal(rows[1].days[0], 'manual');
  assert.equal(delta, 1);
  assert.equal(addCheckedIn({ checked_in: 0 }, -1).checked_in, 0);
});

test('the server answer to a check-in is the truth', () => {
  assert.deepEqual(checkInOutcome({ student: 2, date: '2026-10-05', checked: false }, true), { checked: false, days: null });
  assert.deepEqual(checkInOutcome({ checked: true, days: ['manual'] }, true), { checked: true, days: ['manual'] });
  assert.deepEqual(checkInOutcome(null, true), { checked: true, days: null });
});

test('several check-in cells can be pending at once', () => {
  const none = new Set();
  const a = withPending(none, checkInKey(1, '2026-10-05'), true);
  const ab = withPending(a, checkInKey(2, '2026-10-06'), true);
  assert.deepEqual([...ab], ['1:2026-10-05', '2:2026-10-06']);
  assert.equal(none.size, 0);
  assert.equal(withPending(ab, '1:2026-10-05', true), ab);
  assert.deepEqual([...withPending(ab, '1:2026-10-05', false)], ['2:2026-10-06']);
  assert.equal(withPending(none, 'x', false), none);
});

test('check-in pages: rows, and whether more follow', () => {
  const rows = [{ student: 1, days: [] }, { student: 2, days: [] }];
  assert.deepEqual(checkInPage({ home: { check_ins: { students: rows, students_total: 5 } } }, 0), { rows, hasMore: true, total: 5 });
  assert.equal(checkInPage({ check_ins: { students: rows, students_total: 5 } }, 3).hasMore, false);
  assert.equal(checkInPage({ check_ins: { students: rows, has_more: false, students_total: 99 } }, 0).hasMore, false);
  assert.equal(checkInPage({ check_ins: { results: rows, next: null } }, 0).hasMore, false);
  assert.deepEqual(checkInPage(undefined, 0), { rows: [], hasMore: false, total: null });
  assert.deepEqual(mergeCheckInRows(rows, [{ student: 2, days: [] }, { student: 3, days: [] }]).map((row) => row.student), [1, 2, 3]);
});

test('Review approves each kind through its own endpoint', async () => {
  const calls = [];
  const api = {
    approveTask: (id) => calls.push(['task', id]),
    approveRoadmapMission: (id) => calls.push(['roadmap', id]),
    approveRecord: (endpoint, id) => calls.push([endpoint, id]),
  };
  for (const kind of ['task', 'document', 'roadmap', 'portfolio']) await approveReviewItem(api, kind, 7);
  assert.deepEqual(calls, [['task', 7], ['documents', 7], ['roadmap', 7], ['achievements', 7]]);
  await assert.rejects(approveReviewItem(api, 'essay', 1));
});

test('"You\u2019re all set" shows when nothing waits, once a day per account', () => {
  assert.equal(allClear({ review: 0, needYou: 0, unread: 0 }), true);
  assert.equal(allClear({ review: 1, needYou: 0, unread: 0 }), false);
  assert.equal(allClear({ review: 0, needYou: 0, unread: 3 }), false);
  const storage = memoryStorage();
  assert.equal(allSetSeen(storage, 7, '2026-10-11'), false);
  assert.equal(markAllSetSeen(storage, 7, '2026-10-11'), true);
  assert.equal(allSetSeen(storage, 7, '2026-10-11'), true);
  assert.equal(allSetSeen(storage, 7, '2026-10-12'), false);
  assert.equal(allSetSeen(storage, 8, '2026-10-11'), false);
  const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.equal(allSetSeen(throwing, 7, '2026-10-11'), false);
  assert.equal(markAllSetSeen(throwing, 7, '2026-10-11'), false);
});

test('the 12-week heatmap: weeks as columns, levels by the busiest day', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 8].map((count) => heatLevel(count, 8)), [0, 1, 1, 2, 2, 4]);
  assert.equal(heatLevel(3, 0), 0);
  const weeks = heatmapWeeks({ start: '2026-07-20', end: '2026-10-07', days: { '2026-07-20': 2, '2026-10-05': 4, '2026-10-07': 1 } });
  assert.equal(weeks.length, 12);
  assert.ok(weeks.every((week) => week.length === 7));
  assert.deepEqual(weeks[0][0], { day: '2026-07-20', count: 2, level: 2, future: false, today: false });
  const last = weeks[11];
  assert.equal(last[0].day, '2026-10-05');
  assert.equal(last[0].level, 4);
  assert.deepEqual([last[2].today, last[2].future, last[3].future], [true, false, true]);
  assert.equal(last[6].day, '2026-10-11');
  assert.deepEqual(heatmapWeeks(null), []);
});

test('snapshot choices: students who need you first, then the caseload, once each', () => {
  const choices = snapshotChoices(
    [{ id: 3, name: 'Zarina' }],
    [{ student: 3, name: 'Zarina' }, { student: 1, name: 'Abbos' }],
  );
  assert.deepEqual(choices, [{ id: 3, name: 'Zarina' }, { id: 1, name: 'Abbos' }]);
  assert.deepEqual(snapshotChoices(undefined, undefined), []);
});

test('today\u2019s meetings: the next still to start, else done or under way', () => {
  const now = new Date('2026-10-11T10:00:00Z');
  const meeting = (id, hour, status) => ({ id, status, starts_at: `2026-10-11T${hour}:00:00Z` });
  assert.deepEqual(todayMeetingsState([], now), { state: 'none' });
  assert.deepEqual(todayMeetingsState([meeting(1, '08', 'completed'), meeting(2, '12', 'approved')], now), { state: 'next', meeting: meeting(2, '12', 'approved') });
  // Marked completed early: done, never "next".
  assert.deepEqual(todayMeetingsState([meeting(1, '08', 'completed'), meeting(2, '12', 'completed')], now), { state: 'done' });
  assert.deepEqual(todayMeetingsState([meeting(1, '08', 'completed'), meeting(2, '09', 'approved')], now), { state: 'started' });
});
