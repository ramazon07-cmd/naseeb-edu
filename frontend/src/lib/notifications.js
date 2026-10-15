// The notification bell: where each notice leads, and the unread badge.
// Framework-free so the mapping is unit tested.

import { sectionFromNotice } from './profileSections.js';
import { isPageLocked } from './routes.js';
import { isOpenTask } from './metrics.js';
import { upcomingMeetings } from './meetings.js';
import { USER_STORAGE, userStorageKey } from '../userStorage.js';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

// A parent's bell, built from their /api/parent-portal/ payload (no server notices yet):
// pending invitations, each child's overdue open tasks, and shared meetings in the next 7 days.
export function parentNotices(portal, now = new Date()) {
  const notices = (portal?.pending_invitations || []).map((invitation) => ({ key: `invitation-${invitation.id}`, kind: 'invitation', title: invitation.student_name, page: 'dashboard', childId: null }));
  for (const child of portal?.children || []) {
    const childId = child.profile.id;
    const childName = child.profile.name;
    for (const task of child.tasks.filter((item) => item.is_overdue && isOpenTask(item))) notices.push({ key: `task-${task.id}`, kind: 'task', title: task.title, childName, date: task.due_date, page: 'parent_tasks', childId });
    for (const meeting of upcomingMeetings(child.meetings, now).filter((item) => new Date(item.starts_at) - now <= WEEK_MS)) notices.push({ key: `meeting-${meeting.id}`, kind: 'meeting', title: meeting.topic, childName, date: meeting.starts_at, page: 'parent_meetings', childId });
  }
  return notices;
}

// The family portal shows one child at a time; a parent notice opens its child.
export const PARENT_CHILD_EVENT = 'naseeb:parent-child';
export function selectParentChild(userId, childId) {
  try {localStorage.setItem(userStorageKey(USER_STORAGE.parentChild, userId), String(childId));} catch {/* The event below still switches the open page. */}
  window.dispatchEvent(new CustomEvent(PARENT_CHILD_EVENT, { detail: childId }));
}

// The title the server gives a section that needs changes.
export const PROFILE_CHANGES_TITLE = 'Profile section needs changes';

// Other parts of the app fire this after they mark something read, so the
// bell refreshes its count at once instead of on its next poll.
export const NOTIFICATIONS_CHANGED = 'naseeb:notifications-changed';

// Summary polling: every minute while the tab is visible; each poll that finds
// nothing new waits 1.5x longer, up to five minutes.
export const BELL_POLL = { min: 60_000, max: 300_000, factor: 1.5 };

// The page a notice opens, as { page, params }, or null when it has none.
export function notificationTarget(notification) {
  const id = Number(notification?.target_id);
  const hasId = Number.isInteger(id) && id > 0;
  switch (notification?.kind) {
    // Student notices only (staff use staffNotificationTarget): a locked roadmap has no page to open.
    case 'task': return isPageLocked('roadmap', { role: 'student' }) ? null : { page: 'roadmap', params: { tab: 'tasks' } };
    case 'document': return { page: 'student_center', params: { tab: 'documents' } };
    case 'deadline': return { page: 'applications', params: {} };
    case 'essay': return { page: 'essay_lab', params: hasId ? { essayId: id } : {} };
    case 'meeting': return { page: 'bookings', params: {} };
    case 'message': return { page: 'messages', params: hasId ? { channelId: id } : {} };
    case 'profile_review': {
      // A section sent back opens in edit mode; an approval just shows the cards.
      const section = sectionFromNotice(id);
      return { page: 'student_center', params: section && notification.title === PROFILE_CHANGES_TITLE ? { edit: section.key } : {} };
    }
    default: return null;
  }
}

// A staff notice about submitted work that Review lists (a task or a
// document) opens that item there: 'document-12' for /review?item=document-12.
// Null for every other notice.
const REVIEW_NOTICE_KINDS = new Set(['task', 'document']);

export function reviewItemForNotice(notification) {
  const id = Number(notification?.target_id);
  if (!REVIEW_NOTICE_KINDS.has(notification?.kind) || !Number.isInteger(id) || id <= 0) return null;
  return `${notification.kind}-${id}`;
}

// Everything the bell counts: notices and unread chats.
export function bellTotal(summary) {
  if (!summary) return 0;
  return ['unread', 'chats_unread']
    .reduce((total, key) => total + Math.max(0, Number(summary[key]) || 0), 0);
}

// What a feed does with its unread chats for this summary: 'wait' (none
// yet), 'clear' (the server counts nothing unread) or 'fetch' (ask the server
// for the unread chats; a cached workspace list may be stale).
export function unreadChatsPlan(summary) {
  if (!summary) return 'wait';
  return Math.max(0, Number(summary.chats_unread) || 0) > 0 ? 'fetch' : 'clear';
}

export const unreadChats = (channels) => (Array.isArray(channels) ? channels : []).filter((item) => item.unread_count > 0);

// True when a fresh summary differs from the one on screen.
export function summaryChanged(previous, next) {
  if (!previous || !next) return previous !== next;
  return ['unread', 'chats_unread'].some((key) => previous[key] !== next[key]);
}

export function announceNotificationsChanged(target = typeof window === 'undefined' ? null : window) {
  target?.dispatchEvent?.(new Event(NOTIFICATIONS_CHANGED));
}
