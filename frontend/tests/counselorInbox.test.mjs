import test from 'node:test';
import assert from 'node:assert/strict';
import { counselorOf, markReadFor, unreadFor } from '../src/lib/counselorInbox.js';
import { MESSAGES_TABS, buildPath, parsePath } from '../src/lib/routes.js';

const me = 7;
const thread = [
  { id: 1, sender: 3, recipient: me, is_read: false },
  { id: 2, sender: me, recipient: 3, is_read: false },
  { id: 3, sender: 3, recipient: me, is_read: true },
];

test('only messages sent to the student count as unread', () => {
  assert.equal(unreadFor(thread, me), 1);
  assert.equal(unreadFor(markReadFor(thread, me), me), 0);
  // The student's own messages keep the counselor's read state.
  assert.equal(markReadFor(thread, me)[1].is_read, false);
});

test('continue in chat opens the counselor of the newest message', () => {
  assert.equal(counselorOf(thread, me), 3);
  assert.equal(counselorOf([{ id: 1, sender: me, recipient: 9 }], me), 9);
  assert.equal(counselorOf([], me), null);
});

test('the inbox has its own address', () => {
  assert.deepEqual(MESSAGES_TABS, ['counselor']);
  assert.equal(buildPath({ page: 'messages', params: { tab: 'counselor' } }), '/messages/counselor');
  assert.deepEqual(parsePath('/messages/counselor'), { page: 'messages', params: { tab: 'counselor' } });
  assert.deepEqual(parsePath('/messages/12'), { page: 'messages', params: { channelId: 12 } });
});
