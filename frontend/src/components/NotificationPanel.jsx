import { useEffect, useRef, useState } from 'react';
import { Bell, CalendarClock, CheckCheck, ChevronRight, ClipboardCheck, FileText, ListChecks, MessageCircle, PenLine, Target } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t } from '../i18n';
import { dateTimeText, joinParts } from '../lib/format';
import { sectionFromNotice } from '../lib/profileSections';
import { announceNotificationsChanged, notificationTarget, summaryChanged, unreadChats, unreadChatsPlan } from '../lib/notifications';
import { notificationMessage, notificationTitle } from '../lib/notificationText';
import { usePagedList } from '../hooks/usePagedList';
import { LoadMore, PagedListError, firstPageLoading } from './paged';
import { Empty } from './ui';
import { InlineLoadError } from './states';

export const KIND_ICONS = { task: ClipboardCheck, document: FileText, deadline: Target, essay: PenLine, meeting: CalendarClock, message: MessageCircle, profile_review: ListChecks };

// A section review notice names its section in the reader's language, then the counselor's note.
export function noticeMessage(item) {
  if (item.kind !== 'profile_review') return notificationMessage(item);
  const section = sectionFromNotice(item.target_id);
  return joinParts(section && t(section.title), notificationMessage(item));
}

// Every unread chat opens that conversation (/messages/<id>), not the Messages page.
function ChatNotices({ chats, onOpen }) {
  return chats.map((item) => <button type="button" className="sidebar-notice unread" key={`message-${item.id}`} onClick={() => onOpen('messages', { channelId: item.id })}><MessageCircle size={18} /><span><b>{item.display_name}</b><small>{t('{n} unread', { n: formatNumberLocale(item.unread_count) })}</small></span><ChevronRight size={16} /></button>);
}

// Where a staff member's notice leads: a chat opens itself, a meeting the
// Meetings page, anything else about a student that student's 360.
export function staffNotificationTarget(notification) {
  if (notification.kind === 'message') return notificationTarget(notification);
  if (notification.kind === 'meeting') return { page: 'bookings', params: {} };
  const studentId = Number(notification.student);
  return Number.isInteger(studentId) && studentId > 0 ? { page: 'students', params: { studentId } } : null;
}

// Parents have no server notices: their unread chats only.
function ChatOnlyNotifications({ data, onOpen }) {
  const chats = data.messageChannels.filter((item) => item.unread_count > 0);
  return <>
    <p>{t('Alerts about your work and unread conversations.')}</p>
    <ChatNotices chats={chats} onOpen={onOpen} />
    {!chats.length && <Empty text={t('All caught up')} />}
  </>;
}

// The feed behind the bell and the counselor's Notifications page: the
// server's notices (staff: the ones addressed to them; a student: their own)
// and the unread chats. `summary` is the bell's (/notifications/summary/).
// The unread chats always come from the server (the workspace's cached first
// page may be stale), a page at a time, and clear when it counts none. Each
// time the summary changes, the first page of notices is fetched again and
// merged over the loaded ones, so new notices appear at the top.
export function useNotificationFeed({ summary, notify, staff, pageSize = 20 }) {
  const list = usePagedList('notifications', { filters: staff ? { mine: 'true' } : {}, pageSize });
  const targetOf = staff ? staffNotificationTarget : notificationTarget;
  const [chats, setChats] = useState([]);
  const [chatsNext, setChatsNext] = useState(null);
  const [chatsKnown, setChatsKnown] = useState(false);
  const [chatsError, setChatsError] = useState('');
  const [chatHeadLoading, setChatHeadLoading] = useState(false);
  const [chatsAttempt, setChatsAttempt] = useState(0);
  const lastChatsAttempt = useRef(-1);
  const [loadingChats, setLoadingChats] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const lastSummary = useRef(null);
  // Only the newest unread-chats request may land.
  const chatsRequest = useRef(0);
  const { refreshHead } = list;

  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const plan = unreadChatsPlan(summary);
    if (plan === 'wait') return;
    const previous = lastSummary.current;
    if (previous && !summaryChanged(previous, summary) && lastChatsAttempt.current === chatsAttempt) return;
    lastSummary.current = summary;
    if (previous && summaryChanged(previous, summary)) refreshHead();
    lastChatsAttempt.current = chatsAttempt;
    const request = ++chatsRequest.current;
    const landed = () => mounted.current && request === chatsRequest.current;
    setChatsError('');
    if (plan === 'clear') {
      setChatHeadLoading(false);
      setChats([]);
      setChatsNext(null);
      setChatsKnown(true);
      return;
    }
    setChatHeadLoading(true);
    api.messageChannels('', '', { unread: true }).then((page) => {
      if (!landed()) return;
      setChats(unreadChats(page?.results));
      setChatsNext(page?.next || null);
      setChatsKnown(true);
    }).catch((error) => {
      if (landed()) { setChatsKnown(false); setChatsError(error.message); }
    }).finally(() => { if (landed()) setChatHeadLoading(false); });
  }, [summary, refreshHead, chatsAttempt]);

  async function moreChats() {
    if (!chatsNext || loadingChats) return;
    setLoadingChats(true);
    try {
      const page = await api.pageAt(chatsNext);
      setChats((current) => [...current, ...unreadChats(page?.results).filter((item) => !current.some((known) => known.id === item.id))]);
      setChatsNext(page?.next || null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setLoadingChats(false);
    }
  }

  // Marks the notice read (optimistically) and returns where it leads, or null.
  function read(notification) {
    if (!notification.is_read) {
      list.updateItem(notification.id, (item) => ({ ...item, is_read: true }));
      api.markNotificationRead(notification.id).then(() => announceNotificationsChanged()).catch(() => {
        list.updateItem(notification.id, (item) => ({ ...item, is_read: false }));
      });
    }
    return targetOf(notification);
  }

  async function markAll() {
    if (markingAll) return;
    setMarkingAll(true);
    // Telegram-style: "all" includes the unread chats listed here.
    const read = chats.map((chat) => chat.id);
    try {
      await Promise.all([api.markAllNotificationsRead(), ...read.map((id) => api.markChannelRead(id))]);
      setChats((current) => current.filter((chat) => !read.includes(chat.id)));
      list.reload();
      announceNotificationsChanged();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setMarkingAll(false);
    }
  }

  const empty = chatsKnown && !chatsError && !chatHeadLoading && !(summary?.chats_unread > 0) && !chats.length && !list.items.length && !firstPageLoading(list) && !list.error;
  return { list, targetOf, chats, chatsNext, loadingChats, moreChats, read, markAll, markingAll, empty, chatsError, chatHeadLoading, retryChats: () => setChatsAttempt((value) => value + 1) };
}

function ServerNotifications({ summary, onOpen, notify, staff, onSeeAll }) {
  const feed = useNotificationFeed({ summary, notify, staff });
  const { list, targetOf, chats, chatsNext, loadingChats, moreChats, markAll, markingAll, empty, chatsError, chatHeadLoading, retryChats } = feed;

  function open(notification) {
    const target = feed.read(notification);
    if (target) onOpen(target.page, target.params);
  }

  const hasUnread = (summary?.unread || 0) > 0 || chats.length > 0 || list.items.some((item) => !item.is_read);
  return <>
    <div className="notification-panel-head">
      <p>{t('Alerts about your work and unread conversations.')}</p>
      {hasUnread && <button type="button" className="button quiet small" onClick={markAll} disabled={markingAll} aria-busy={markingAll}><CheckCheck size={15} /> {t('Mark all as read')}</button>}
    </div>
    {chatsError && <InlineLoadError message={chatsError} onRetry={retryChats} />}
    {chatHeadLoading && <p role="status">{t('Loading…')}</p>}
    <ChatNotices chats={chats} onOpen={onOpen} />
    {chatsNext && <button type="button" className="button quiet small" onClick={moreChats} disabled={loadingChats} aria-busy={loadingChats}>{loadingChats ? t('Loading…') : t('Load more')}</button>}
    {list.items.map((item) => {
      const Icon = KIND_ICONS[item.kind] || Bell;
      const target = targetOf(item);
      return <button type="button" key={item.id} className={`sidebar-notice ${item.is_read ? '' : 'unread'}`} onClick={() => open(item)}>
        <Icon size={18} />{!item.is_read && <em className="sr-only">{t('Unread')}</em>}
        <span><b>{notificationTitle(item)}</b><small>{noticeMessage(item)}</small><small className="notice-time">{dateTimeText(item.created_at)}</small></span>
        {target ? <ChevronRight size={16} /> : !item.is_read && <i className="sidebar-unread-dot" />}
      </button>;
    })}
    {firstPageLoading(list) && <p role="status">{t('Loading…')}</p>}
    <PagedListError list={list} />
    <LoadMore list={list} />
    {empty && <Empty text={t('All caught up')} />}
    {onSeeAll && <button type="button" className="button quiet small notification-see-all" onClick={onSeeAll}>{t('See all notifications')} <ChevronRight size={15} /></button>}
  </>;
}

// `onSeeAll`: opens the full Notifications page (the counselor workspace has one).
export function NotificationPanel({ user, data, summary, onOpen, notify, onSeeAll }) {
  return <div className="sidebar-utility-panel notification-panel">
    {user.role === 'parent' ? <ChatOnlyNotifications {...{ data, onOpen }} /> : <ServerNotifications {...{ summary, onOpen, notify, onSeeAll }} staff={user.role !== 'student'} />}
  </div>;
}
