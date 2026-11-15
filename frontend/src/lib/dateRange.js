// Date-range helpers for the counselor's "Invitees can schedule within…" setting.
// Days are plain "YYYY-MM-DD" calendar keys, compared as strings (they sort
// the same as dates); nothing here depends on the browser's time zone.

const parts = (key) => { const [year, month, day] = key.split('-').map(Number); return { year, month, day }; };

// A day nobody can book any more: strictly before `today`.
export const isPastDay = (key, today) => key < today;

// One click on a calendar day. The first click (or any click once a range is
// complete) starts a new range; the second ends it, and a second click before
// the start becomes the new start. Past days are ignored.
export function pickRangeDay(range, key, today) {
  const { start = null, end = null } = range || {};
  if (isPastDay(key, today)) return { start, end };
  if (!start || end) return { start: key, end: null };
  if (key < start) return { start: key, end: null };
  return { start, end: key };
}

export const isRangeStart = (key, range) => Boolean(range?.start) && key === range.start;
export const isRangeEnd = (key, range) => Boolean(range?.end) && key === range.end;
// Strictly between the two ends (they have their own, solid look).
export const isRangeBetween = (key, range) => Boolean(range?.start && range?.end) && key > range.start && key < range.end;

// "16 Nov – 22 Nov 2026"; the year shows on both ends when they differ; one day → "16 Nov 2026".
// `month(index)` gives the short month name, so the caller picks the language.
export function rangeText(start, end, month = (index) => ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][index]) {
  if (!start) return '';
  const from = parts(start);
  const day = (value) => `${value.day} ${month(value.month - 1)}`;
  if (!end || end === start) return `${day(from)} ${from.year}`;
  const to = parts(end);
  return from.year === to.year ? `${day(from)} – ${day(to)} ${to.year}` : `${day(from)} ${from.year} – ${day(to)} ${to.year}`;
}

// The window the weekly-availability API stores, as the form edits it.
export function windowFromApi(data = {}) {
  return {
    mode: data.window_mode === 'range' ? 'range' : 'rolling',
    days: String(data.window_days ?? 60),
    start: data.window_start || null,
    end: data.window_end || null,
  };
}

// Payload fields for PUT; the unused side is sent as null/default so the API keeps one consistent window.
export function windowToApi({ mode, days, start, end }) {
  return mode === 'range'
    ? { window_mode: 'range', window_days: Number(days) || 60, window_start: start, window_end: end || start }
    : { window_mode: 'rolling', window_days: Number(days), window_start: null, window_end: null };
}

// '' when the window is fine, else a short code the form turns into a message.
export function windowProblem({ mode, days, start, end }, today) {
  if (mode === 'range') {
    if (!start) return 'range_missing';
    if ((end || start) < start) return 'range_order';
    if ((end || start) < today) return 'range_past';
    return '';
  }
  const count = Number(days);
  return days === '' || !Number.isInteger(count) || count < 1 || count > 365 ? 'days' : '';
}
