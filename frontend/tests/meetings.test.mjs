import test from 'node:test';
import assert from 'node:assert/strict';
import { isOpenMeeting, meetingStatus, meetingsForTab, studentMeetingsForTab, upcomingMeetings } from '../src/lib/meetings.js';

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
