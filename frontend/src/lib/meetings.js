// Meeting (booking) rules shared by the dashboard, the Meetings page and the
// family portal; the backend twin is documented in docs/metrics.md.

const OPEN_STATUSES = ['pending', 'approved'];

const startsAfter = (item, now) => new Date(item.starts_at) > now;

// Pending or approved and not started: can still happen, be cancelled or moved.
export const isOpenMeeting = (item, now = new Date()) => OPEN_STATUSES.includes(item?.status) && startsAfter(item, now);

// A meeting a staff member proposed that the STUDENT has not answered yet.
export const isAwaitingStudent = (item, now = new Date()) => Boolean(item?.staff_requested) && item?.status === 'pending' && !isExpiredMeeting(item, now) && startsAfter(item, now);

// The API flags a request nobody confirmed before it started; the fallback
// covers a page left open past the start time.
export const isExpiredMeeting = (item, now = new Date()) => Boolean(item?.is_expired) || (item?.status === 'pending' && !startsAfter(item, now));

// `student: true` is the student's Meetings page only: an approved meeting
// whose time has passed was never marked completed by staff, so it reads as
// past rather than "Approved". Other callers keep the stored status.
export const meetingStatus = (item, now = new Date(), { student = false } = {}) => {
  if (isExpiredMeeting(item, now)) return 'expired_unconfirmed';
  if (student && item.status === 'approved' && !startsAfter(item, now)) return 'past_unmarked';
  return item.status;
};

export const upcomingMeetings = (items = [], now = new Date()) => items.filter((item) => isOpenMeeting(item, now)).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));

// The word a meeting's badge shows: "Confirmed", not "Approved" — the same
// vocabulary a student sees (labels.js already has both words; every other
// approve/reject flow in the app keeps "Approved").
export const meetingBadgeStatus = (status) => status === 'approved' ? 'confirmed' : status;

// Staff Meetings page: requests waiting for a decision, oldest request first.
export const pendingMeetings = (items = [], now = new Date()) => items.
filter((item) => item.status === 'pending' && !item.staff_requested && isOpenMeeting(item, now)).
sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

// Staff Meetings page: everything starting in the next 7 days, any status,
// soonest first — a pending request due this week shows up here too — then
// what happened in the last 7 days and still needs the counselor: an expired or
// declined request to rebook, a confirmed meeting nobody marked completed, a
// completed one (its notes are written right after).
export const meetingsThisWeek = (items = [], now = new Date()) => {
  const at = (item) => new Date(item.starts_at);
  const weekEnd = new Date(now.getTime() + 7 * 86400000);
  const weekStart = new Date(now.getTime() - 7 * 86400000);
  const upcoming = items.filter((item) => at(item) >= now && at(item) < weekEnd).sort((a, b) => at(a) - at(b));
  const overdue = items.
  filter((item) => at(item) < now && at(item) >= weekStart && (needsRebook(item, now) || ['approved', 'completed'].includes(item.status))).
  sort((a, b) => at(b) - at(a));
  return [...upcoming, ...overdue];
};

// Counselor Meetings list: everything already loaded, split at "now". Upcoming is soonest first, past newest first.
export function splitMeetingsByTime(items = [], now = new Date()) {
  const time = (item) => new Date(item.starts_at).getTime();
  const upcoming = items.filter((item) => time(item) >= now.getTime()).sort((a, b) => time(a) - time(b));
  const past = items.filter((item) => time(item) < now.getTime()).sort((a, b) => time(b) - time(a));
  return { upcoming, past };
}

// Consecutive meetings on the same calendar day (`dayOf` gives the day key): [{ key, items }, …] in the given order.
export function groupMeetingsByDay(items = [], dayOf = (value) => String(value).slice(0, 10)) {
  const groups = [];
  for (const item of items) {
    const key = dayOf(item.starts_at);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(item);
    else groups.push({ key, items: [item] });
  }
  return groups;
}

// A meeting nobody will ever hold as scheduled: start fresh with "Rebook"
// rather than try to move it (an expired request can't be rescheduled — see
// BookingViewSet.reschedule's has_started guard).
export const needsRebook = (item, now = new Date()) => ['rejected', 'cancelled'].includes(item.status) || isExpiredMeeting(item, now);

export function meetingsForTab(items = [], tab, staff, now = new Date()) {
  return items.filter((item) => {
    const open = isOpenMeeting(item, now);
    if (tab === 'pending') return open && item.status === 'pending';
    if (tab === 'upcoming') return open && (!staff || item.status === 'approved');
    return !open;
  });
}

// Student Meetings page: Upcoming soonest first with invitations waiting for the
// student's answer on top, Past newest first.
export function studentMeetingsForTab(items = [], tab, now = new Date()) {
  const time = (item) => new Date(item.starts_at).getTime();
  const waiting = (item) => (isAwaitingStudent(item, now) ? 0 : 1);
  const order = tab === 'upcoming' ? (a, b) => waiting(a) - waiting(b) || time(a) - time(b) : (a, b) => time(b) - time(a);
  return meetingsForTab(items, tab, false, now).sort(order);
}

// The API says who cancelled when it knows; a student's own cancel reads
// "Cancelled by student" on the counselor's list.
export const cancelledByStudent = (item) => item?.status === 'cancelled' && (
  item.cancelled_by_role === 'student' || item.cancelled_by === 'student' || (item.cancelled_by != null && item.cancelled_by === item.student)
);

// "5 booked · 2 cancelled this week": cancelled and declined ones are not booked.
export function weekCounts(items = []) {
  const booked = items.filter((item) => ['pending', 'approved', 'completed'].includes(item.status) && !item.is_expired).length;
  const cancelled = items.filter((item) => item.status === 'cancelled').length;
  return { booked, cancelled };
}

// Booked meetings per calendar day, in day order: [['2026-11-17', 2], …]. `dayOf` turns a start into its day key.
export function bookedPerDay(items = [], dayOf = (value) => String(value).slice(0, 10)) {
  const counts = new Map();
  for (const item of items) {
    if (!['pending', 'approved', 'completed'].includes(item.status) || item.is_expired) continue;
    const key = dayOf(item.starts_at);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts].sort(([a], [b]) => (a < b ? -1 : 1));
}

// Staff who can publish meeting hours (the backend's BOOKING_STAFF_ROLES): their Meetings page shows their own
// booking page, with the preview as a student and the shareable link.
export const OWNS_MEETING_HOURS = ['counselor', 'assistant', 'teacher', 'organization'];
export const ownsMeetingHours = (user) => OWNS_MEETING_HOURS.includes(user?.role);

// The link a student opens to book one staff member: the Meetings page with that person's dialog already open.
export const bookingLink = (origin, participantId) => `${String(origin).replace(/\/+$/, '')}/meetings?book=${participantId}`;

// The staff id a Meetings address asks for (?book=7), or null.
export function bookParam(search) {
  const value = new URLSearchParams(search || '').get('book');
  return /^[1-9]\d{0,9}$/.test(value || '') ? Number(value) : null;
}

const addDays = (key, days) => {
  const [year, month, day] = key.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
};

// First and last day (inclusive, Tashkent calendar days like the server) students may book under these
// weekly-availability settings; `first` can be past `last` once a range has ended.
export function bookingWindow(settings, today) {
  if (settings?.window_mode === 'range' && settings.window_start && settings.window_end) {
    return { first: settings.window_start > today ? settings.window_start : today, last: settings.window_end };
  }
  return { first: today, last: addDays(today, Number(settings?.window_days ?? 60)) };
}

// A staff member's overview calendar: { 'YYYY-MM-DD': { free: [slot], booked: [meeting] } } in the viewer's zone.
// Free times are the upcoming, unrequested slots inside the booking window (what students can take, before the
// minimum notice); booked ones are every upcoming pending or approved meeting, window or not.
export function overviewDays({ slots = [], bookings = [], settings, now = new Date(), dayOf, windowDayOf }) {
  const days = new Map();
  const day = (key) => { if (!days.has(key)) days.set(key, { free: [], booked: [] }); return days.get(key); };
  const { first, last } = bookingWindow(settings, windowDayOf(now));
  const byStart = (x, y) => new Date(x.starts_at) - new Date(y.starts_at);
  for (const slot of [...slots].sort(byStart)) {
    const inside = windowDayOf(slot.starts_at);
    if (slot.available && new Date(slot.starts_at) > now && inside >= first && inside <= last) day(dayOf(slot.starts_at)).free.push(slot);
  }
  for (const meeting of [...bookings].sort(byStart)) {
    if (isOpenMeeting(meeting, now)) day(dayOf(meeting.starts_at)).booked.push(meeting);
  }
  return days;
}

// Where a staff member opens a booked student's profile (the Students page, record route /students/<profile id>).
export const studentProfilePath = (studentId) => `/students/${studentId}`;

// The t.me address of a Telegram @username, or '' when the student has none.
export const telegramUrl = (username) => (/^[A-Za-z0-9_]{1,32}$/.test(String(username ?? '')) ? `https://t.me/${username}` : '');
