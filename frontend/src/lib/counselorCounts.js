// The numbers behind the counselor workspace: the sidebar badges, Home's cards
// and Review's filters. Lists are keyset-paged and carry no total, so exact
// counts come from the dashboard stats (counselor_summary.py). The browser holds
// only a window of bookings and the first page of chats, so counting those is
// the fallback for an API without stats.badges.
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

// The server's badge numbers (stats.badges), or null when this API has none yet.
export function statsBadges(stats) {
  const badges = stats?.badges;
  if (!badges || typeof badges !== 'object') return null;
  const value = (key) => (badges[key] === undefined || badges[key] === null ? null : count(badges[key]));
  return {
    meetings: value('meetings_pending'), messages: value('messages_unread'),
    conversations: value('messages_unread_conversations'), messageStudents: value('messages_unread_students'),
  };
}

// Conversations with an unread message: the server's count, else the loaded chats'.
export function unreadConversations(stats, channels) {
  return statsBadges(stats)?.conversations ?? unreadMessages(channels).conversations;
}

// `bell`: the notification summary (/notifications/summary/), whose `unread`
// counts the notices addressed to this counselor. Meetings and messages come
// from stats.badges when the server sends them, so the badges stay exact
// without loading every booking and channel; otherwise from what is loaded.
// The Messages badge and the bell count conversations, not messages.
export function counselorCounts(stats, data, now = new Date(), bell = null) {
  const badges = statsBadges(stats);
  const conversations = unreadConversations(stats, data?.messageChannels);
  return {
    review: reviewCounts(stats).total,
    essays: count(stats?.review?.essays),
    meetings: badges?.meetings ?? pendingMeetings(data?.bookings, now).length,
    // Students who joined by invite and wait for confirmation (Recently joined).
    students: count(stats?.badges?.students_pending),
    messages: conversations,
    // The bell lists unread conversations and the counselor's unread notices (see NotificationPanel).
    notifications: conversations + count(bell?.unread),
  };
}

// Which of a counselor's live collections the minute poll reloads after a
// fresh stats response. The page on screen keeps its own list current; other
// lists reload only when their badge moved. Without server badges (an older
// API) both reload every time, as before.
export function liveReloadKeys(page, previousStats, nextStats) {
  const before = statsBadges(previousStats);
  const after = statsBadges(nextStats);
  const keys = new Set();
  if (page === 'bookings') keys.add('bookings');
  if (page === 'messages') keys.add('messageChannels');
  if (after?.meetings == null || (before && before.meetings !== after.meetings)) keys.add('bookings');
  if (after?.messages == null || (before && (before.messages !== after.messages || before.messageStudents !== after.messageStudents))) keys.add('messageChannels');
  return [...keys];
}
