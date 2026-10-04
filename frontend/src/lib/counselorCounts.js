// The numbers behind the counselor workspace: the sidebar badges, Home's cards
// and Review's filters. Lists are keyset-paged and carry no total, so exact
// counts come from the dashboard stats (counselor_summary.py); what the browser
// already holds (bookings, chat channels) is counted here.
import { pendingMeetings } from './meetings.js';

const count = (value) => Math.max(0, Number(value) || 0);

// Review's kinds, in the order of its filter pills, and the stats field of each.
export const REVIEW_KINDS = ['task', 'document', 'roadmap', 'portfolio'];
const REVIEW_STAT = { task: 'tasks', document: 'documents', roadmap: 'roadmap', portfolio: 'portfolio' };

export function reviewCounts(stats) {
  const byKind = Object.fromEntries(REVIEW_KINDS.map((kind) => [kind, count(stats?.review?.[REVIEW_STAT[kind]])]));
  return { ...byKind, total: Object.values(byKind).reduce((sum, value) => sum + value, 0) };
}

export function unreadMessages(channels = []) {
  const unread = channels.filter((item) => item.unread_count > 0);
  return { messages: unread.reduce((sum, item) => sum + count(item.unread_count), 0), conversations: unread.length };
}

export function counselorCounts(stats, data, now = new Date()) {
  const { messages, conversations } = unreadMessages(data?.messageChannels);
  return {
    review: reviewCounts(stats).total,
    essays: count(stats?.review?.essays),
    meetings: pendingMeetings(data?.bookings, now).length,
    messages,
    // Staff notices are the unread conversations (see NotificationPanel's staff view).
    notifications: conversations,
  };
}
