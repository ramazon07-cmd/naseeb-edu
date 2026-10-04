// Meeting (booking) rules shared by the dashboard, the Meetings page and the
// family portal; the backend twin is documented in docs/metrics.md.

const OPEN_STATUSES = ['pending', 'approved'];

const startsAfter = (item, now) => new Date(item.starts_at) > now;

// Pending or approved and not started: can still happen, be cancelled or moved.
export const isOpenMeeting = (item, now = new Date()) => OPEN_STATUSES.includes(item?.status) && startsAfter(item, now);

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
filter((item) => item.status === 'pending' && isOpenMeeting(item, now)).
sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

// Staff Meetings page: everything starting in the next 7 days, any status,
// soonest first — a pending request due this week shows up here too — then
// what happened in the last 7 days and still needs the counselor: an expired or
// declined request to rebook, a confirmed meeting nobody marked completed.
export const meetingsThisWeek = (items = [], now = new Date()) => {
  const at = (item) => new Date(item.starts_at);
  const weekEnd = new Date(now.getTime() + 7 * 86400000);
  const weekStart = new Date(now.getTime() - 7 * 86400000);
  const upcoming = items.filter((item) => at(item) >= now && at(item) < weekEnd).sort((a, b) => at(a) - at(b));
  const overdue = items.
  filter((item) => at(item) < now && at(item) >= weekStart && (needsRebook(item, now) || item.status === 'approved')).
  sort((a, b) => at(b) - at(a));
  return [...upcoming, ...overdue];
};

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

// Student Meetings page: Upcoming soonest first, Past newest first.
export function studentMeetingsForTab(items = [], tab, now = new Date()) {
  const time = (item) => new Date(item.starts_at).getTime();
  const order = tab === 'upcoming' ? (a, b) => time(a) - time(b) : (a, b) => time(b) - time(a);
  return meetingsForTab(items, tab, false, now).sort(order);
}
