import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage } = await import('../src/i18n.js');
const { counselorCounts, liveReloadKeys, reviewCounts, statsBadges, unreadConversations, unreadMessages } = await import('../src/lib/counselorCounts.js');
const { studentReasons, needsAttention, isOnTrack, isQuiet, urgency } = await import('../src/lib/studentReasons.js');
const { mergeReviewQueue, REVIEW_SOURCES } = await import('../src/lib/reviewQueue.js');
const { meetingsThisWeek } = await import('../src/lib/meetings.js');
const { activityText } = await import('../src/lib/activityText.js');
const { COUNSELOR_NAV, navigationFor, reachablePages, canOpenPage, isPageLocked, parsePath, resolveRoute } = await import('../src/lib/routes.js');

const now = new Date('2026-09-25T12:00:00Z');

test('review counts come from the stats, one number per Review kind', () => {
  const stats = { review: { tasks: 2, documents: 3, roadmap: 1, portfolio: 4, essays: 5 } };
  assert.deepEqual(reviewCounts(stats), { task: 2, document: 3, roadmap: 1, portfolio: 4, total: 10 });
  // Essays have their own badge and never count towards Review.
  assert.equal(counselorCounts(stats, {}).essays, 5);
  assert.equal(counselorCounts(stats, {}).review, 10);
  assert.deepEqual(reviewCounts(null), { task: 0, document: 0, roadmap: 0, portfolio: 0, total: 0 });
  assert.deepEqual(reviewCounts({ review: { tasks: -3, documents: 'x' } }), { task: 0, document: 0, roadmap: 0, portfolio: 0, total: 0 });
});

test('badges count pending requests and unread messages from what the browser holds', () => {
  const data = {
    bookings: [
      { id: 1, status: 'pending', starts_at: '2026-09-26T09:00:00Z', created_at: '2026-09-24T09:00:00Z' },
      { id: 2, status: 'approved', starts_at: '2026-09-26T10:00:00Z', created_at: '2026-09-24T09:00:00Z' },
      { id: 3, status: 'pending', starts_at: '2026-09-24T09:00:00Z', created_at: '2026-09-23T09:00:00Z', is_expired: true },
    ],
    messageChannels: [{ unread_count: 2 }, { unread_count: 0 }, { unread_count: 3 }],
  };
  const counts = counselorCounts({}, data, now);
  assert.equal(counts.meetings, 1);
  assert.deepEqual(unreadMessages(data.messageChannels), { messages: 5, conversations: 2 });
  // The Messages badge counts conversations, like the bell.
  assert.equal(counts.messages, 2);
  assert.equal(counts.notifications, 2);
  // The bell adds the notices addressed to the counselor.
  assert.equal(counselorCounts({}, data, now, { unread: 3, chats_unread: 5 }).notifications, 5);
  assert.equal(counselorCounts({}, data, now, { unread: -1 }).notifications, 2);
});

test('with server badges, meetings and messages come from the stats, not the loaded lists', () => {
  const data = { bookings: [{ id: 1, status: 'pending', starts_at: '2026-09-26T09:00:00Z' }], messageChannels: [{ unread_count: 2 }] };
  const stats = { badges: { meetings_pending: 7, messages_unread: 40, messages_unread_conversations: 9, messages_unread_students: 12 } };
  const counts = counselorCounts(stats, data, now, { unread: 1 });
  assert.equal(counts.meetings, 7);
  // Unread chats beyond the loaded first page still count: conversations come from the server.
  assert.equal(counts.messages, 9);
  assert.equal(counts.notifications, 10);
  assert.deepEqual(statsBadges(stats), { meetings: 7, messages: 40, conversations: 9, messageStudents: 12 });
  assert.equal(unreadConversations(stats, []), 9);
  assert.equal(statsBadges({}), null);
  // A missing or broken field falls back to what is loaded.
  const partial = counselorCounts({ badges: { meetings_pending: null, messages_unread_conversations: -2 } }, data, now);
  assert.equal(partial.meetings, 1);
  assert.equal(partial.messages, 0);
  assert.equal(counselorCounts({ badges: { meetings_pending: 1 } }, data, now).messages, 1);
});

test('the poll reloads meetings and chats only on their page or when their badge moved', () => {
  const at = (meetings, messages, students = 0) => ({ badges: { meetings_pending: meetings, messages_unread: messages, messages_unread_students: students } });
  assert.deepEqual(liveReloadKeys('dashboard', at(1, 2), at(1, 2)), []);
  assert.deepEqual(liveReloadKeys('bookings', at(1, 2), at(1, 2)), ['bookings']);
  assert.deepEqual(liveReloadKeys('messages', at(1, 2), at(1, 2)), ['messageChannels']);
  assert.deepEqual(liveReloadKeys('students', at(1, 2), at(2, 2)), ['bookings']);
  assert.deepEqual(liveReloadKeys('students', at(1, 2), at(1, 3)), ['messageChannels']);
  assert.deepEqual(liveReloadKeys('students', at(1, 2, 1), at(1, 2, 2)), ['messageChannels']);
  // The first stats seen this session: the lists loaded at sign-in are current.
  assert.deepEqual(liveReloadKeys('dashboard', null, at(1, 2)), []);
  // An API without badges: both reload, as before.
  assert.deepEqual(liveReloadKeys('dashboard', {}, {}), ['bookings', 'messageChannels']);
});

test('"need you" means late or missing, not merely waiting for review', () => {
  const late = studentReasons({ tasks_overdue: 1, to_review_total: 2 }, now);
  assert.deepEqual(late.map((reason) => reason.key), ['late_task', 'to_review']);
  assert.ok(needsAttention(late));

  const reviewOnly = studentReasons({ to_review_total: 1 }, now);
  assert.ok(!needsAttention(reviewOnly) && !isOnTrack(reviewOnly));

  assert.ok(isOnTrack(studentReasons({}, now)));
  // Roadmap missions are not shown on the counselor side, so late ones are no reason.
  assert.ok(isOnTrack(studentReasons({ missions_overdue: 2 }, now)));
});

test('a single missing document is named, several are counted', () => {
  const one = studentReasons({ documents_missing: 1, missing_document_title: 'Passport' }, now)[0];
  assert.deepEqual([one.key, one.tone, one.title], ['missing_document', 'danger', 'Passport']);
  const many = studentReasons({ documents_missing: 3, missing_document_title: 'Passport' }, now)[0];
  assert.deepEqual([many.count, many.title], [3, '']);
});

test('a quiet spell starts at 14 days and is not urgent by itself', () => {
  const days = (n) => ({ user_detail: { last_login: new Date(now.getTime() - n * 86400000).toISOString() } });
  assert.ok(!isQuiet(studentReasons(days(13), now)));
  assert.ok(isQuiet(studentReasons(days(14), now)));
  assert.ok(!needsAttention(studentReasons(days(30), now)));
  // A student who never signed in has no last login: that is not "quiet".
  assert.ok(isOnTrack(studentReasons({ user_detail: { last_login: null } }, now)));
});

test('students sort most urgent first: late or missing, then review, then quiet', () => {
  const rows = [
    ['quiet', studentReasons({ user_detail: { last_login: '2026-08-01T00:00:00Z' } }, now)],
    ['review', studentReasons({ to_review_total: 1 }, now)],
    ['late+missing', studentReasons({ tasks_overdue: 1, documents_missing: 1 }, now)],
    ['late', studentReasons({ tasks_overdue: 1 }, now)],
    ['fine', []],
  ];
  rows.sort((a, b) => urgency(b[1]) - urgency(a[1]));
  assert.deepEqual(rows.map(([name]) => name), ['late+missing', 'late', 'review', 'quiet', 'fine']);
});

test('the review queue merges every kind oldest first and keeps what an action call needs', () => {
  const queue = mergeReviewQueue({
    tasks: [{ id: 7, title: 'PS draft', student: 1, student_name: 'Ramazon', submitted_at: '2026-09-23T10:00:00Z' }],
    documents: [{ id: 7, title: 'IELTS', student: 2, student_name: 'Aziza', updated_at: '2026-09-22T10:00:00Z' }],
    roadmapMissions: [{ id: 3, title: 'Shortlist', student: 1, student_name: 'Ramazon', updated_at: '2026-09-24T10:00:00Z' }],
    achievements: [{ id: 9, title: 'Olympiad', student: 3, student_name: 'Sevara', created_at: '2026-09-21T10:00:00Z' }],
  });
  assert.deepEqual(queue.map((item) => item.id), ['portfolio-9', 'document-7', 'task-7', 'roadmap-3']);
  const task = queue.find((item) => item.kind === 'task');
  assert.deepEqual([task.recordId, task.endpoint, task.studentId, task.studentName], [7, 'tasks', 1, 'Ramazon']);
  assert.equal(task.record.title, 'PS draft');
  // Every source has a slot in the pills, the tags and the pattern for its count.
  for (const source of REVIEW_SOURCES) assert.ok(source.label && source.pill && source.when.includes('{when}') && source.countPattern.includes('|'));
});

test('this week: what is coming, then what happened lately and still needs the counselor', () => {
  const meeting = (id, status, starts_at, extra = {}) => ({ id, status, starts_at, ...extra });
  const week = meetingsThisWeek([
    meeting(1, 'approved', '2026-09-27T09:00:00Z'),
    meeting(2, 'pending', '2026-09-26T09:00:00Z'),
    meeting(3, 'pending', '2026-09-24T09:00:00Z', { is_expired: true }), // expired: rebook it
    meeting(4, 'approved', '2026-09-23T09:00:00Z'),                      // held, never marked completed
    meeting(5, 'completed', '2026-09-24T09:00:00Z'),                      // finished: notes still to write
    meeting(6, 'cancelled', '2026-09-22T09:00:00Z'),                      // cancelled: rebook it
    meeting(7, 'approved', '2026-09-10T09:00:00Z'),                       // too old for "this week"
    meeting(8, 'approved', '2026-10-30T09:00:00Z'),                       // too far ahead
  ], now);
  assert.deepEqual(week.map((item) => item.id), [2, 1, 3, 5, 4, 6]);
});

test('known server activity sentences are rewritten, unknown ones are kept', () => {
  setLanguage('uz');
  assert.notEqual(activityText('Task approved: Personal Statement 1 - draft (+100 XP)'), 'Task approved: Personal Statement 1 - draft (+100 XP)');
  assert.match(activityText('Task approved: Personal Statement 1 - draft (+100 XP)'), /Personal Statement 1 - draft.*100 XP/);
  assert.match(activityText('Level approved: 1 → 2'), /1 → 2/);
  assert.equal(activityText('Something the server invented'), 'Something the server invented');
  setLanguage('en');
  assert.equal(activityText('Document sent back: Passport scan'), 'Document sent back: Passport scan');
  assert.equal(activityText('Student completed their profile'), 'Completed their profile');
});

test('the counselor sidebar includes a locked Roadmap; other old flat pages stay reachable but unlisted', () => {
  const counselor = { id: 2, role: 'counselor' };
  assert.deepEqual(COUNSELOR_NAV, ['dashboard', 'students', 'tasks', 'review', 'essays', 'bookings', 'messages', 'counselor_roadmap']);
  assert.deepEqual(navigationFor(counselor), [...COUNSELOR_NAV, 'support']);
  for (const page of ['documents', 'portfolio', 'certificates', 'recommendations']) {
    assert.ok(!navigationFor(counselor).includes(page), `${page} is not in the sidebar`);
    assert.ok(canOpenPage(page, counselor), `${page} still opens by link`);
  }
  // Teachers and schools never gain the counselor's old pages this way.
  assert.ok(!reachablePages({ id: 3, role: 'teacher' }).has('documents'));
  assert.ok(!reachablePages({ id: 4, role: 'organization' }).has('certificates'));
});

test('roadmap templates stay locked for counselors and hidden from admins', () => {
  const counselor = { id: 2, role: 'counselor' };
  const admin = { id: 1, role: 'admin' };
  assert.ok(navigationFor(counselor).includes('counselor_roadmap'));
  assert.equal(isPageLocked('counselor_roadmap', counselor), true);
  assert.ok(!navigationFor(admin).includes('counselor_roadmap'));
  for (const user of [counselor, admin]) {
    assert.equal(canOpenPage('counselor_roadmap', user), false, user.id);
  }
  assert.deepEqual(resolveRoute(parsePath('/counselor-roadmap'), counselor), { page: 'dashboard', params: {} });
  assert.deepEqual(resolveRoute(parsePath('/counselor-roadmap'), admin), { page: 'admin_dashboard', params: {} });
});
