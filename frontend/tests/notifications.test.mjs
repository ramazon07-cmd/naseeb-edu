import test from 'node:test';
import assert from 'node:assert/strict';
import { BELL_POLL, NOTIFICATIONS_CHANGED, announceNotificationsChanged, bellTotal, notificationTarget, reviewItemForNotice, summaryChanged, unreadChats, unreadChatsPlan } from '../src/lib/notifications.js';
import { nextPollDelay } from '../src/lib/pollDelay.js';
import { buildPath, canOpenPage, parsePath } from '../src/lib/routes.js';

test('each notice kind opens the page that holds its work', () => {
  const cases = [
    [{ kind: 'document' }, '/student-center/documents'],
    [{ kind: 'deadline' }, '/applications'],
    [{ kind: 'essay', target_id: 42 }, '/essay-lab/essays/42'],
    [{ kind: 'essay', target_id: null }, '/essay-lab'],
    [{ kind: 'meeting' }, '/meetings'],
    [{ kind: 'message', target_id: 9 }, '/messages/9'],
    [{ kind: 'profile_review', target_id: 3, title: 'Profile section needs changes' }, '/student-center?edit=tests'],
    [{ kind: 'profile_review', target_id: 2, title: 'Profile section approved' }, '/student-center'],
    [{ kind: 'profile_review', target_id: 99, title: 'Profile section needs changes' }, '/student-center'],
    [{ kind: 'message', target_id: 'x' }, '/messages'],
  ];
  for (const [notice, path] of cases) {
    const target = notificationTarget(notice);
    assert.equal(buildPath(target), path, notice.kind);
    // The link survives a refresh: the path parses back to the same page.
    assert.equal(parsePath(path.split('?')[0]).page, target.page);
  }
  // The roadmap is locked for students, so a task notice has no page to open (no dead click).
  assert.equal(notificationTarget({ kind: 'task' }), null);
  assert.equal(notificationTarget({ kind: 'general' }), null);
  assert.equal(notificationTarget(null), null);
});

test('the bell counts notices and unread chats, not the legacy counselor thread', () => {
  assert.equal(bellTotal(null), 0);
  assert.equal(bellTotal({ unread: 2, counselor_messages_unread: 1, chats_unread: 4 }), 6);
  assert.equal(bellTotal({ unread: -1, chats_unread: 'x' }), 0);
});

test('only a different summary counts as a change', () => {
  const summary = { unread: 1, chats_unread: 2 };
  assert.equal(summaryChanged(null, summary), true);
  assert.equal(summaryChanged(summary, { ...summary }), false);
  assert.equal(summaryChanged(summary, { ...summary, chats_unread: 3 }), true);
});

test('bell polling backs off to five minutes and never polls faster than a minute', () => {
  let delay = BELL_POLL.min;
  for (let i = 0; i < 10; i += 1) delay = nextPollDelay(delay, false, BELL_POLL);
  assert.equal(delay, BELL_POLL.max);
  assert.equal(nextPollDelay(delay, true, BELL_POLL), BELL_POLL.min);
  assert.ok(BELL_POLL.min >= 60_000);
});

test('marking something read tells the bell to refresh', () => {
  const events = [];
  announceNotificationsChanged({ dispatchEvent: (event) => events.push(event.type) });
  assert.deepEqual(events, [NOTIFICATIONS_CHANGED]);
  assert.doesNotThrow(() => announceNotificationsChanged(null));
});

test('a staff notice about a task or document opens that item in Review', () => {
  assert.equal(reviewItemForNotice({ kind: 'document', target_id: 12 }), 'document-12');
  assert.equal(reviewItemForNotice({ kind: 'task', target_id: '7' }), 'task-7');
  assert.equal(reviewItemForNotice({ kind: 'essay', target_id: 3 }), null);
  assert.equal(reviewItemForNotice({ kind: 'document', target_id: null }), null);
  assert.equal(reviewItemForNotice({ kind: 'task', target_id: 0 }), null);
  assert.equal(reviewItemForNotice(null), null);
});

test('counselors have a Notifications page at /notifications', () => {
  assert.deepEqual(parsePath('/notifications'), { page: 'notifications', params: {} });
  assert.equal(buildPath({ page: 'notifications' }), '/notifications');
  assert.equal(buildPath({ page: 'review', params: { item: reviewItemForNotice({ kind: 'document', target_id: 4 }) } }), '/review?item=document-4');
});

test('only a counselor workspace opens the Notifications page', () => {
  assert.equal(canOpenPage('notifications', { id: 1, role: 'counselor' }), true);
  for (const user of [{ id: 2, role: 'student' }, { id: 3, role: 'teacher' }, { id: 4, role: 'parent' }, { id: 5, role: 'counselor', is_superuser: true }]) {
    assert.equal(canOpenPage('notifications', user), false, user.role);
  }
});

test('unread chats come from the server and clear when it counts none', () => {
  assert.equal(unreadChatsPlan(null), 'wait');
  assert.equal(unreadChatsPlan({ unread: 3, chats_unread: 0 }), 'clear');
  assert.equal(unreadChatsPlan({ unread: 0 }), 'clear');
  assert.equal(unreadChatsPlan({ unread: 0, chats_unread: 2 }), 'fetch');
  assert.deepEqual(unreadChats([{ id: 1, unread_count: 2 }, { id: 2, unread_count: 0 }]), [{ id: 1, unread_count: 2 }]);
  assert.deepEqual(unreadChats(undefined), []);
});
