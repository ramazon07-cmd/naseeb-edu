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
