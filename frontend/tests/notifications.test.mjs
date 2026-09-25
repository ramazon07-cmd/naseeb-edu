import test from 'node:test';
import assert from 'node:assert/strict';
import { BELL_POLL, NOTIFICATIONS_CHANGED, announceNotificationsChanged, bellTotal, notificationTarget, summaryChanged } from '../src/lib/notifications.js';
import { nextPollDelay } from '../src/lib/pollDelay.js';
import { buildPath, parsePath, roadmapTab } from '../src/lib/routes.js';

test('each notice kind opens the page that holds its work', () => {
  const cases = [
    [{ kind: 'task' }, '/roadmap/tasks'],
    [{ kind: 'document' }, '/student-center/documents'],
    [{ kind: 'deadline' }, '/applications'],
    [{ kind: 'essay', target_id: 42 }, '/essay-lab/essays/42'],
    [{ kind: 'essay', target_id: null }, '/essay-lab'],
    [{ kind: 'meeting' }, '/meetings'],
    [{ kind: 'message', target_id: 9 }, '/messages/9'],
    [{ kind: 'message', target_id: 'x' }, '/messages'],
  ];
  for (const [notice, path] of cases) {
    const target = notificationTarget(notice);
    assert.equal(buildPath(target), path, notice.kind);
    // The link survives a refresh: the path parses back to the same page.
    assert.equal(parsePath(path).page, target.page);
  }
  // A task notice lands on the student's own Tasks tab, not the role default.
  assert.equal(roadmapTab(notificationTarget({ kind: 'task' }).params.tab, false), 'tasks');
  assert.equal(notificationTarget({ kind: 'general' }), null);
  assert.equal(notificationTarget(null), null);
});

test('the bell counts notices, counselor messages and unread chats', () => {
  assert.equal(bellTotal(null), 0);
  assert.equal(bellTotal({ unread: 2, counselor_messages_unread: 1, chats_unread: 4 }), 7);
  assert.equal(bellTotal({ unread: -1, counselor_messages_unread: 'x' }), 0);
});

test('only a different summary counts as a change', () => {
  const summary = { unread: 1, counselor_messages_unread: 0, chats_unread: 2 };
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
