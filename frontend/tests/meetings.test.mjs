import test from 'node:test';
import assert from 'node:assert/strict';
import { bookParam, bookingLink, bookingWindow, overviewDays, ownsMeetingHours, isAwaitingStudent, isOpenMeeting, meetingStatus, meetingsForTab, pendingMeetings, studentMeetingsForTab, upcomingMeetings } from '../src/lib/meetings.js';

const now = new Date('2026-09-25T12:00:00Z');
const meeting = (id, status, starts_at, extra = {}) => ({ id, status, starts_at, ...extra });
const items = [
  meeting(1, 'pending', '2026-09-26T09:00:00Z'),
  meeting(2, 'approved', '2026-09-27T09:00:00Z'),
  meeting(3, 'pending', '2026-09-24T09:00:00Z', { is_expired: true }),
  meeting(4, 'cancelled', '2026-09-28T09:00:00Z'),
  meeting(5, 'approved', '2026-09-20T09:00:00Z'),
  meeting(6, 'rejected', '2026-09-29T09:00:00Z'),
  meeting(7, 'completed', '2026-09-19T09:00:00Z'),
];
const ids = (list) => list.map((item) => item.id);

test('only pending or approved meetings that have not started are open', () => {
  assert.deepEqual(ids(items.filter((item) => isOpenMeeting(item, now))), [1, 2]);
  assert.deepEqual(ids(upcomingMeetings([...items].reverse(), now)), [1, 2]);
});

test('a pending request past its start reads as expired, not pending', () => {
  assert.equal(meetingStatus(items[2], now), 'expired_unconfirmed');
  // A page left open past the start time does not wait for the API flag.
  assert.equal(meetingStatus(meeting(8, 'pending', '2026-09-25T11:59:00Z'), now), 'expired_unconfirmed');
  assert.equal(meetingStatus(items[0], now), 'pending');
  assert.equal(meetingStatus(items[3], now), 'cancelled');
});

test('tabs: cancelled and expired requests land in History', () => {
  assert.deepEqual(ids(meetingsForTab(items, 'upcoming', false, now)), [1, 2]);
  assert.deepEqual(ids(meetingsForTab(items, 'history', false, now)), [3, 4, 5, 6, 7]);
  assert.deepEqual(ids(meetingsForTab(items, 'pending', true, now)), [1]);
  assert.deepEqual(ids(meetingsForTab(items, 'upcoming', true, now)), [2]);
  assert.deepEqual(ids(meetingsForTab(items, 'history', true, now)), [3, 4, 5, 6, 7]);
});

test('student view: a past meeting still approved reads as not marked completed', () => {
  assert.equal(meetingStatus(items[4], now, { student: true }), 'past_unmarked');
  assert.equal(meetingStatus(items[1], now, { student: true }), 'approved');
  assert.equal(meetingStatus(items[2], now, { student: true }), 'expired_unconfirmed');
  assert.equal(meetingStatus(items[6], now, { student: true }), 'completed');
  // Parent and staff pages keep the stored status.
  assert.equal(meetingStatus(items[4], now), 'approved');
});

test('student tabs: Upcoming soonest first, Past newest first', () => {
  const shuffled = [items[6], items[1], items[3], items[0], items[4], items[2], items[5]];
  assert.deepEqual(ids(studentMeetingsForTab(shuffled, 'upcoming', now)), [1, 2]);
  assert.deepEqual(ids(studentMeetingsForTab(shuffled, 'history', now)), [6, 4, 3, 5, 7]);
  // The shared helper keeps its input order for other pages.
  assert.deepEqual(ids(meetingsForTab(shuffled, 'history', false, now)), [7, 4, 5, 3, 6]);
});

test('a staff invitation waits for the student and sits on top of their Upcoming', () => {
  const invite = meeting(10, 'pending', '2026-09-30T09:00:00Z', { staff_requested: true });
  const confirmed = meeting(11, 'approved', '2026-09-28T09:00:00Z');
  assert.equal(isAwaitingStudent(invite, now), true);
  assert.equal(isAwaitingStudent(items[0], now), false); // a student's own request waits for staff
  assert.equal(isAwaitingStudent({ ...invite, status: 'approved' }, now), false);
  assert.equal(isAwaitingStudent({ ...invite, starts_at: '2026-09-24T09:00:00Z' }, now), false); // expired
  assert.deepEqual(ids(studentMeetingsForTab([confirmed, items[0], invite], 'upcoming', now)), [10, 1, 11]);
});

test('staff: an invitation is not a request waiting for the counselor', () => {
  const invite = meeting(10, 'pending', '2026-09-30T09:00:00Z', { staff_requested: true, created_at: '2026-09-25T08:00:00Z' });
  assert.deepEqual(ids(pendingMeetings([invite, items[0]], now)), [1]);
  // It still counts as an open meeting for the staff member's views.
  assert.equal(isOpenMeeting(invite, now), true);
});

test('the booking link is the Meetings page with ?book=<staff id>, and only a real id is read back', () => {
  assert.equal(bookingLink('https://app.example.com', 7), 'https://app.example.com/meetings?book=7');
  assert.equal(bookingLink('https://app.example.com/', 7), 'https://app.example.com/meetings?book=7');
  assert.equal(bookParam('?book=7'), 7);
  assert.equal(bookParam('?lang=uz&book=42'), 42);
  for (const bad of ['', '?book=', '?book=0', '?book=-3', '?book=abc', '?book=7;drop', '?book=99999999999', '?book=1.5']) assert.equal(bookParam(bad), null, bad);
});

test('every role that can own meeting hours gets the booking page; students and admins do not', () => {
  for (const role of ['counselor', 'assistant', 'teacher', 'organization']) assert.equal(ownsMeetingHours({ role }), true, role);
  for (const role of ['student', 'parent', 'admin']) assert.equal(ownsMeetingHours({ role }), false, role);
  assert.equal(ownsMeetingHours(null), false);
});

test('the booking window: a range (clipped to today) or the next N days', () => {
  assert.deepEqual(bookingWindow({ window_mode: 'range', window_start: '2026-11-16', window_end: '2026-11-22' }, '2026-11-12'), { first: '2026-11-16', last: '2026-11-22' });
  assert.deepEqual(bookingWindow({ window_mode: 'range', window_start: '2026-11-01', window_end: '2026-11-22' }, '2026-11-12'), { first: '2026-11-12', last: '2026-11-22' });
  assert.deepEqual(bookingWindow({ window_mode: 'rolling', window_days: 60 }, '2026-11-12'), { first: '2026-11-12', last: '2027-01-11' });
  assert.deepEqual(bookingWindow(undefined, '2026-12-30'), { first: '2026-12-30', last: '2027-02-28' });
});

test('overview days: free times inside the window, open meetings anywhere, in the viewer zone', () => {
  const at = new Date('2026-11-12T08:00:00Z');
  const china = (value) => new Date(new Date(value).getTime() + 8 * 3600000).toISOString().slice(0, 10);
  const tashkent = (value) => new Date(new Date(value).getTime() + 5 * 3600000).toISOString().slice(0, 10);
  const slot = (id, starts_at, available = true) => ({ id, starts_at, available, duration_minutes: 45 });
  const settings = { window_mode: 'range', window_start: '2026-11-16', window_end: '2026-11-22' };
  const days = overviewDays({
    slots: [
      slot(1, '2026-11-16T16:00:00Z'), // Tashkent 21:00 on the 16th, China 00:00 on the 17th
      slot(2, '2026-11-16T16:45:00Z', false), // taken by a meeting: not a free time
      slot(3, '2026-11-23T10:00:00Z'), // after the window
      slot(4, '2026-11-12T07:00:00Z'), // already past
      slot(5, '2026-11-15T10:00:00Z'), // before the window
    ],
    bookings: [
      meeting(10, 'approved', '2026-11-16T16:45:00Z', { student_name: 'Ali' }),
      meeting(11, 'cancelled', '2026-11-17T10:00:00Z'),
      meeting(12, 'pending', '2026-11-30T10:00:00Z'),
    ],
    settings, now: at, dayOf: china, windowDayOf: tashkent,
  });
  assert.deepEqual([...days.keys()].sort(), ['2026-11-17', '2026-11-30']);
  assert.deepEqual(days.get('2026-11-17').free.map((item) => item.id), [1]);
  assert.deepEqual(days.get('2026-11-17').booked.map((item) => item.id), [10]);
  assert.deepEqual(days.get('2026-11-30').booked.map((item) => item.id), [12]);
});
