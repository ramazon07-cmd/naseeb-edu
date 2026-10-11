// Counselor Home: which cards show and in what order (kept per account in
// localStorage), and the small rules the cards share. Translation-free, like
// reviewQueue.js: the page turns keys into words.
import { userStorageKey } from '../userStorage.js';

export const HOME_CARDS = ['stats', 'review', 'need_you', 'snapshot', 'today', 'deadlines', 'check_ins', 'progress'];
// Cards that span the whole Home width rather than one column of the grid.
export const WIDE_CARDS = ['stats'];
export const HOME_LAYOUT_STORAGE = 'naseeb-counselor-home-v1';

export const DEFAULT_LAYOUT = Object.freeze({ order: HOME_CARDS, hidden: [] });

// Whatever was stored (an older card list, junk, nothing): known cards once
// each, in the stored order. A card added since goes where the default order
// puts it: right after the card it follows there (first when none does).
export function normalizeLayout(value) {
  const order = Array.isArray(value?.order) ? value.order : [];
  const known = [...new Set(order.filter((id) => HOME_CARDS.includes(id)))];
  const hidden = Array.isArray(value?.hidden) ? [...new Set(value.hidden.filter((id) => HOME_CARDS.includes(id)))] : [];
  const merged = [...known];
  HOME_CARDS.forEach((id, index) => {
    if (merged.includes(id)) return;
    const before = HOME_CARDS.slice(0, index).reverse().find((other) => merged.includes(other));
    merged.splice(before ? merged.indexOf(before) + 1 : 0, 0, id);
  });
  return { order: merged, hidden };
}

const storageOf = (storage) => {
  try { return typeof storage === 'function' ? storage() : storage; } catch { return null; }
};

export function loadLayout(storage, userId) {
  try {
    const raw = storageOf(storage)?.getItem(userStorageKey(HOME_LAYOUT_STORAGE, userId));
    return normalizeLayout(raw ? JSON.parse(raw) : null);
  } catch {
    return normalizeLayout(null);
  }
}

export function saveLayout(storage, userId, layout) {
  try {
    storageOf(storage)?.setItem(userStorageKey(HOME_LAYOUT_STORAGE, userId), JSON.stringify(normalizeLayout(layout)));
    return true;
  } catch {
    return false;
  }
}

export function toggleCard(layout, id) {
  const hidden = layout.hidden.includes(id) ? layout.hidden.filter((item) => item !== id) : [...layout.hidden, id];
  return { ...layout, hidden };
}

export function moveCard(layout, id, delta) {
  const order = [...layout.order];
  const from = order.indexOf(id);
  const to = from + delta;
  if (from < 0 || to < 0 || to >= order.length) return layout;
  [order[from], order[to]] = [order[to], order[from]];
  return { ...layout, order };
}

export const visibleCards = (layout) => layout.order.filter((id) => !layout.hidden.includes(id));

export function greetingKey(hour) {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

// A day in the check-in grid. `auto` days come from the counselor's own work
// and cannot be un-ticked; future days cannot be ticked.
export function checkInAction(state, day, today) {
  if (day > today) return null;
  if (state === 'auto') return null;
  return state === 'manual' ? 'off' : 'on';
}

// `checked_in` counts every student, not only the rows on screen (the server
// sends the first ~50), so it moves by the one row that changed. `days`: the
// row's days as the server reports them, when it does.
export function setCheckInRow(rows, studentId, dayIndex, checked, days = null) {
  let delta = 0;
  const next = rows.map((row) => {
    if (row.student !== studentId) return row;
    const serverDays = Array.isArray(days) && days.length === row.days.length;
    const updated = serverDays ? [...days] : [...row.days];
    if (!serverDays && updated[dayIndex] !== 'auto') updated[dayIndex] = checked ? 'manual' : null;
    delta = Number(updated.some(Boolean)) - Number(row.days.some(Boolean));
    return { ...row, days: updated };
  });
  return { rows: next, delta };
}

export const addCheckedIn = (checkIns, delta) => ({ ...checkIns, checked_in: Math.max(0, (Number(checkIns.checked_in) || 0) + delta) });

export function setCheckIn(checkIns, studentId, dayIndex, checked, days = null) {
  const { rows, delta } = setCheckInRow(checkIns.students, studentId, dayIndex, checked, days);
  return addCheckedIn({ ...checkIns, students: rows }, delta);
}

// The state a check-in request leaves: the server's answer
// ({student, date, checked[, days]}) wins over what was asked.
export function checkInOutcome(response, requested) {
  return {
    checked: typeof response?.checked === 'boolean' ? response.checked : requested,
    days: Array.isArray(response?.days) ? response.days : null,
  };
}

export const checkInKey = (studentId, day) => `${studentId}:${day}`;

// Cells with a request in flight: several may be, one per cell.
export function withPending(pending, key, busy) {
  if (busy === pending.has(key)) return pending;
  const next = new Set(pending);
  if (busy) next.add(key); else next.delete(key);
  return next;
}

// One page of `?check_ins=all&limit=&offset=`: the rows and whether more follow.
// Reads `home.check_ins` or a bare `check_ins` block.
export function checkInPage(payload, offset = 0) {
  const block = payload?.home?.check_ins ?? payload?.check_ins ?? payload ?? {};
  const rows = Array.isArray(block.students) ? block.students : Array.isArray(block.results) ? block.results : [];
  const total = Number(block.students_total);
  const hasMore = typeof block.has_more === 'boolean' ? block.has_more
    : block.next !== undefined ? Boolean(block.next)
      : Number.isFinite(total) && rows.length > 0 && offset + rows.length < total;
  return { rows, hasMore, total: Number.isFinite(total) ? total : null };
}

// Rows shown after "Show all": Home's own rows, then later pages (once each).
export function mergeCheckInRows(first, more) {
  const seen = new Set(first.map((row) => row.student));
  return [...first, ...more.filter((row) => !seen.has(row.student) && seen.add(row.student))];
}

export const checkedDays = (row) => row.days.filter(Boolean).length;

// Shares of the progress bar, in whole percent that add up to 100 (0 when empty).
export function bucketShares(buckets = {}) {
  const keys = ['on_track', 'behind', 'needs_attention'];
  const total = keys.reduce((sum, key) => sum + (Number(buckets[key]) || 0), 0);
  if (!total) return Object.fromEntries(keys.map((key) => [key, 0]));
  const shares = Object.fromEntries(keys.map((key) => [key, Math.floor(((Number(buckets[key]) || 0) * 100) / total)]));
  let rest = 100 - keys.reduce((sum, key) => sum + shares[key], 0);
  for (const key of [...keys].sort((a, b) => (buckets[b] || 0) - (buckets[a] || 0))) {
    if (!rest) break;
    if (buckets[key]) { shares[key] += 1; rest -= 1; }
  }
  return shares;
}

// Server reasons ({key, count, title}) in the shape counselorUi's reasonText reads.
const REASON_PATTERNS = {
  late_task: '{n} late task|{n} late tasks',
  late_mission: '{n} late mission|{n} late missions',
};
export const homeReasons = (reasons = []) => reasons.map((reason) => ({
  ...reason, tone: 'danger', countPattern: REASON_PATTERNS[reason.key],
}));

// The Today card's line under "N meetings" (today's approved and completed
// meetings): the next one still to start, else 'done' when every one was marked
// completed, 'started' when some are under way, 'none' without meetings.
export function todayMeetingsState(meetings = [], now = new Date()) {
  if (!meetings.length) return { state: 'none' };
  const next = meetings.find((meeting) => meeting.status !== 'completed' && new Date(meeting.starts_at) > now);
  if (next) return { state: 'next', meeting: next };
  return { state: meetings.every((meeting) => meeting.status === 'completed') ? 'done' : 'started' };
}

// -- "You're all set!" ---------------------------------------------------

export const ALL_SET_STORAGE = 'naseeb-counselor-all-set-v1';

// Nothing waits: no review, nobody who needs the counselor, no unread message.
export const allClear = ({ review = 0, needYou = 0, unread = 0 } = {}) => !review && !needYou && !unread;

// Shown once a day: the day it was last dismissed is kept per account.
export function allSetSeen(storage, userId, day) {
  try {
    return storageOf(storage)?.getItem(userStorageKey(ALL_SET_STORAGE, userId)) === day;
  } catch {
    return false;
  }
}

export function markAllSetSeen(storage, userId, day) {
  try {
    storageOf(storage)?.setItem(userStorageKey(ALL_SET_STORAGE, userId), day);
    return true;
  } catch {
    return false;
  }
}

// -- "Last 12 weeks" heatmap ----------------------------------------------

const DAY_MS = 86400000;
const isoDay = (time) => new Date(time).toISOString().slice(0, 10);
const dayTime = (iso) => Date.parse(`${iso}T00:00:00Z`);

// 0 for no check-in, else 1..4 by share of the busiest day.
export function heatLevel(count, max) {
  if (!count || !max) return 0;
  return Math.min(4, Math.max(1, Math.ceil((count / max) * 4)));
}

// `history`: {start (a Monday), end (today), days: {date: students}} from the
// server. Columns are weeks, Monday first; days after `end` are `future`.
export function heatmapWeeks(history) {
  if (!history?.start || !history?.end) return [];
  const days = history.days || {};
  const max = Math.max(0, ...Object.values(days).map(Number));
  const start = dayTime(history.start);
  const end = dayTime(history.end);
  const weeks = [];
  for (let time = start; time <= end; time += 7 * DAY_MS) {
    weeks.push(Array.from({ length: 7 }, (_, index) => {
      const day = isoDay(time + index * DAY_MS);
      const count = Number(days[day]) || 0;
      return { day, count, level: heatLevel(count, max), future: time + index * DAY_MS > end, today: day === history.end };
    }));
  }
  return weeks;
}

// -- Student snapshot -----------------------------------------------------

// Who the snapshot can show: students who need the counselor first, then the
// check-in rows (the caseload, needs-you first), each once.
export function snapshotChoices(needYou = [], checkInRows = []) {
  const seen = new Set();
  return [
    ...needYou.map((student) => ({ id: student.id, name: student.name })),
    ...checkInRows.map((row) => ({ id: row.student, name: row.name })),
  ].filter((choice) => !seen.has(choice.id) && seen.add(choice.id));
}
