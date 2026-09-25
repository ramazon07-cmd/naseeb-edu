import { useEffect, useState } from 'react';
import { Bell, CalendarClock, CheckCheck, ChevronRight, ClipboardCheck, FileText, MessageCircle, PenLine, Target, UserRound } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t } from '../i18n';
import { dateText, dateTimeText } from '../lib/format';
import { isOpenTask, nextPriorities } from '../lib/metrics';
import { announceNotificationsChanged, notificationTarget } from '../lib/notifications';
import { usePagedList } from '../hooks/usePagedList';
import { LoadMore, PagedListError, firstPageLoading } from './paged';
import { Empty } from './ui';

const KIND_ICONS = { task: ClipboardCheck, document: FileText, deadline: Target, essay: PenLine, meeting: CalendarClock, message: MessageCircle };

// `linkChat`: open that chat rather than the Messages page (student portal).
function ChatNotices({ chats, onOpen, linkChat = false }) {
  return chats.map((item) => <button type="button" className="sidebar-notice unread" key={`message-${item.id}`} onClick={() => onOpen('messages', linkChat ? { channelId: item.id } : {})}><MessageCircle size={18} /><span><b>{item.display_name}</b><small>{formatNumberLocale(item.unread_count)} {t('Unread')}</small></span><ChevronRight size={16} /></button>);
}

// Staff keep the previous panel: unread chats and upcoming work.
function StaffNotifications({ data, onOpen }) {
  const chats = data.messageChannels.filter((item) => item.unread_count > 0);
  return <>
    <p>{t('Unread conversations and upcoming work.')}</p>
    <ChatNotices chats={chats} onOpen={onOpen} />
    {nextPriorities(data.tasks).slice(0, 5).map((item) => <button type="button" className="sidebar-notice" key={`task-${item.id}`} onClick={() => onOpen('roadmap')}><ClipboardCheck size={18} /><span><b>{item.title}</b><small>{dateText(item.due_date)}</small></span><ChevronRight size={16} /></button>)}
    {!chats.length && !data.tasks.some(isOpenTask) && <Empty text={t('All caught up')} />}
  </>;
}

function StudentNotifications({ data, summary, onOpen, notify }) {
  const list = usePagedList('notifications', { pageSize: 20 });
  const [chats, setChats] = useState(() => data.messageChannels.filter((item) => item.unread_count > 0));
  const [markingAll, setMarkingAll] = useState(false);
  const chatsUnread = summary?.chats_unread || 0;
  const counselorUnread = summary?.counselor_messages_unread || 0;

  // The workspace's channel list is loaded once; fetch it fresh when the
  // server says there is something unread.
  useEffect(() => {
    if (!chatsUnread) return undefined;
    let active = true;
    api.messageChannels().then((items) => {
      if (active) setChats((items || []).filter((item) => item.unread_count > 0));
    }).catch(() => {});
    return () => { active = false; };
  }, [chatsUnread]);

  function open(notification) {
    if (!notification.is_read) {
      list.updateItem(notification.id, (item) => ({ ...item, is_read: true }));
      api.markNotificationRead(notification.id).then(() => announceNotificationsChanged()).catch(() => {
        list.updateItem(notification.id, (item) => ({ ...item, is_read: false }));
      });
    }
    const target = notificationTarget(notification);
    if (target) onOpen(target.page, target.params);
  }

  async function markAll() {
    if (markingAll) return;
    setMarkingAll(true);
    try {
      await api.markAllNotificationsRead();
      list.reload();
      announceNotificationsChanged();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setMarkingAll(false);
    }
  }

  const hasUnread = (summary?.unread || 0) > 0 || list.items.some((item) => !item.is_read);
  const empty = !chats.length && !counselorUnread && !list.items.length && !firstPageLoading(list) && !list.error;
  return <>
    <div className="notification-panel-head">
      <p>{t('Alerts about your work and unread conversations.')}</p>
      {hasUnread && <button type="button" className="button quiet small" onClick={markAll} disabled={markingAll} aria-busy={markingAll}><CheckCheck size={15} /> {t('Mark all as read')}</button>}
    </div>
    <ChatNotices chats={chats} onOpen={onOpen} linkChat />
    {counselorUnread > 0 && <button type="button" className="sidebar-notice unread" onClick={() => onOpen('messages', { tab: 'counselor' })}><UserRound size={18} /><span><b>{t('From your counselor')}</b><small>{formatNumberLocale(counselorUnread)} {t('Unread')}</small></span><ChevronRight size={16} /></button>}
    {list.items.map((item) => {
      const Icon = KIND_ICONS[item.kind] || Bell;
      const target = notificationTarget(item);
      return <button type="button" key={item.id} className={`sidebar-notice ${item.is_read ? '' : 'unread'}`} onClick={() => open(item)}>
        <Icon size={18} />{!item.is_read && <em className="sr-only">{t('Unread')}</em>}
        <span><b>{t(item.title)}</b><small>{item.message}</small><small className="notice-time">{dateTimeText(item.created_at)}</small></span>
        {target ? <ChevronRight size={16} /> : !item.is_read && <i className="sidebar-unread-dot" />}
      </button>;
    })}
    {firstPageLoading(list) && <p role="status">{t('Loading…')}</p>}
    <PagedListError list={list} />
    <LoadMore list={list} />
    {empty && <Empty text={t('All caught up')} />}
  </>;
}

export function NotificationPanel({ user, data, summary, onOpen, notify }) {
  return <div className="sidebar-utility-panel notification-panel">
    {user.role === 'student' ? <StudentNotifications {...{ data, summary, onOpen, notify }} /> : <StaffNotifications {...{ data, onOpen }} />}
  </div>;
}
