// The notification bell: where each notice leads, and the unread badge.
// Framework-free so the mapping is unit tested.

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
    case 'task': return { page: 'roadmap', params: { tab: 'tasks' } };
    case 'document': return { page: 'student_center', params: { tab: 'documents' } };
    case 'deadline': return { page: 'applications', params: {} };
    case 'essay': return { page: 'essay_lab', params: hasId ? { essayId: id } : {} };
    case 'meeting': return { page: 'bookings', params: {} };
    case 'message': return { page: 'messages', params: hasId ? { channelId: id } : {} };
    default: return null;
  }
}

// Everything the bell counts: notices, the counselor inbox and unread chats.
export function bellTotal(summary) {
  if (!summary) return 0;
  return ['unread', 'counselor_messages_unread', 'chats_unread']
    .reduce((total, key) => total + Math.max(0, Number(summary[key]) || 0), 0);
}

// True when a fresh summary differs from the one on screen.
export function summaryChanged(previous, next) {
  if (!previous || !next) return previous !== next;
  return ['unread', 'counselor_messages_unread', 'chats_unread'].some((key) => previous[key] !== next[key]);
}

export function announceNotificationsChanged(target = typeof window === 'undefined' ? null : window) {
  target?.dispatchEvent?.(new Event(NOTIFICATIONS_CHANGED));
}
