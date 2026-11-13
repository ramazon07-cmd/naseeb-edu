import { useCallback, useEffect, useState } from 'react';
import { Bell, CheckCheck, ChevronRight, Clock3, MessageCircle } from 'lucide-react';
import { api } from '../api';
import { formatDateLocale, formatNumberLocale, t } from '../i18n';
import { dateTimeText, joinParts } from '../lib/format';
import { NOTIFICATIONS_CHANGED, reviewItemForNotice } from '../lib/notifications';
import { notificationTitle } from '../lib/notificationText';
import { KIND_ICONS, noticeMessage, useNotificationFeed } from '../components/NotificationPanel';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { CxHead } from '../components/counselorUi';
import { invalidatePagedLists } from '../hooks/usePagedList';
import { BlueButton, DateTile, EmptyState, GlassCard, KpiRow, KpiTile, PageHeader } from '../design/blue/ui';
import '../design/pages/dashboard-blue.css';

// The counselor's full notification list ("What happened since your last
// visit"): unread chats first, then the notices addressed to them, newest
// first, a page at a time. The bell's panel is the short version of this.
// `user` is passed for students, who get the blue design and their own notices
// (not the staff `mine` filter); staff callers omit it.
export function NotificationsPage({ notify, setPage, user }) {
  return user?.role === 'student' ? <StudentNotifications {...{ notify, setPage }} /> : <StaffNotifications {...{ notify, setPage }} />;
}

const dayParts = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { day: '', month: '' };
  return { day: String(date.getDate()), month: formatDateLocale(value, { month: 'short' }).replace(/\bSept\b/, 'Sep').replace(/\.$/, '') };
};

// Everything both lists share: the unread summary (kept fresh by the bell's
// change event), the notice + chat feed, and the cleanup that stops notices read
// here from coming back unread from the page cache (Back, the bell).
function useNotificationsPageData({ staff, notify }) {
  const [summary, setSummary] = useState(null);
  const loadSummary = useCallback(() => api.notificationSummary().then(setSummary).catch(() => {}), []);
  useEffect(() => {
    loadSummary();
    window.addEventListener(NOTIFICATIONS_CHANGED, loadSummary);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, loadSummary);
  }, [loadSummary]);
  const feed = useNotificationFeed({ summary, notify, staff });
  useEffect(() => () => invalidatePagedLists(['notifications']), []);
  return { summary, feed };
}

function StudentNotifications({ notify, setPage }) {
  const { summary, feed } = useNotificationsPageData({ staff: false, notify });
  const { list, chats, chatsNext, loadingChats, moreChats, markAll, markingAll, empty } = feed;
  function open(notification) {
    const target = feed.read(notification);
    if (target) setPage(target.page, target.params);
  }
  const unreadNotices = summary?.unread ?? list.items.filter((item) => !item.is_read).length;
  const hasUnread = unreadNotices > 0 || chats.length > 0 || list.items.some((item) => !item.is_read);
  return <div className="nb-notif">
    <PageHeader title={t('Notifications')} subtitle={t('Alerts about your work and unread conversations.')}
      actions={hasUnread ? <BlueButton variant="ghost" size="sm" icon={CheckCheck} onClick={markAll} disabled={markingAll} aria-busy={markingAll}>{t('Mark all as read')}</BlueButton> : null} />
    <KpiRow columns={2} label={t('Summary')}>
      <KpiTile tone={0} icon={Bell} value={formatNumberLocale(unreadNotices)} label={t('Unread alerts')} />
      <KpiTile tone={1} icon={MessageCircle} value={formatNumberLocale(summary?.chats_unread ?? chats.length)} label={t('Unread chats')} />
    </KpiRow>
    <GlassCard tone="solid" className="nb-notif-card" title={t('Notifications')} icon={Bell}>
      {(chats.length > 0 || list.items.length > 0) && <ul className="nb-notif-list">
        {chats.map((chat) => <li key={`chat-${chat.id}`}>
          <button type="button" className="nb-notif-row is-unread" onClick={() => setPage('messages', { channelId: chat.id })}>
            <span className="nb-notif-icon" aria-hidden="true"><MessageCircle size={20} /></span>
            <span className="nb-notif-copy"><b>{chat.display_name}</b><small>{t('{n} unread', { n: formatNumberLocale(chat.unread_count) })}</small></span>
            <em className="nb-notif-go">{t('Open chat')}</em>
          </button>
        </li>)}
        {list.items.map((item) => {
          const Icon = KIND_ICONS[item.kind] || Bell;
          const target = feed.targetOf(item);
          return <li key={item.id}>
            <button type="button" className={`nb-notif-row${item.is_read ? '' : ' is-unread'}`} onClick={() => open(item)}>
              <DateTile {...dayParts(item.created_at)} hot={!item.is_read} />
              <span className="nb-notif-copy">
                <b><Icon size={16} aria-hidden="true" />{notificationTitle(item)}{!item.is_read && <em className="sr-only">{t('Unread')}</em>}</b>
                {noticeMessage(item) && <span>{noticeMessage(item)}</span>}
                <small><Clock3 size={13} aria-hidden="true" />{dateTimeText(item.created_at)}</small>
              </span>
              {!item.is_read && <i className="nb-notif-dot" aria-hidden="true" />}
              {target && <ChevronRight size={18} className="nb-notif-chevron" aria-hidden="true" />}
            </button>
          </li>;
        })}
      </ul>}
      {chatsNext && <div className="nb-notif-more"><BlueButton variant="ghost" size="sm" onClick={moreChats} disabled={loadingChats} aria-busy={loadingChats}>{loadingChats ? t('Loading…') : t('Load more')}</BlueButton></div>}
      {firstPageLoading(list) && <p className="nb-dash-note" role="status">{t('Loading…')}</p>}
      <PagedListError list={list} />
      <LoadMore list={list} />
      {empty && <EmptyState icon={Bell} title={t('You are all caught up.')} />}
    </GlassCard>
  </div>;
}

function StaffNotifications({ notify, setPage }) {
  const { summary, feed } = useNotificationsPageData({ staff: false, notify });
  const { list, chats, chatsNext, loadingChats, moreChats, markAll, markingAll, empty } = feed;

  function open(notification) {
    const item = reviewItemForNotice(notification);
    const target = feed.read(notification);
    if (item) setPage('review', { item });
    else if (target) setPage(target.page, target.params);
  }

  const hasUnread = (summary?.unread || 0) > 0 || chats.length > 0 || list.items.some((item) => !item.is_read);
  return <div className="cx-page cx-notices-page">
    <CxHead title={t('Notifications')} subtitle={t('What happened since your last visit')}>
      {hasUnread && <button type="button" className="cx-btn" onClick={markAll} disabled={markingAll} aria-busy={markingAll}><CheckCheck size={15} aria-hidden="true" />{t('Mark all as read')}</button>}
    </CxHead>
    <section className="cx-card cx-notices" aria-label={t('Notifications')}>
      {(chats.length > 0 || list.items.length > 0) && <ul className="cx-notice-list">
        {chats.map((chat) => <li key={`chat-${chat.id}`}>
          <button type="button" className="cx-notice unread" onClick={() => setPage('messages', { channelId: chat.id })}>
            <i className="cx-notice-dot" aria-hidden="true" />
            <span className="cx-notice-icon" aria-hidden="true"><MessageCircle size={17} /></span>
            <span className="cx-notice-copy"><b>{chat.display_name}</b><small>{t('{n} unread', { n: formatNumberLocale(chat.unread_count) })}</small></span>
            <span className="cx-notice-action">{t('Open chat')}</span>
          </button>
        </li>)}
        {list.items.map((item) => {
          const Icon = KIND_ICONS[item.kind] || Bell;
          const reviewItem = reviewItemForNotice(item);
          const target = reviewItem || feed.targetOf(item);
          return <li key={item.id}>
            <button type="button" className={`cx-notice${item.is_read ? '' : ' unread'}`} onClick={() => open(item)}>
              <i className="cx-notice-dot" aria-hidden="true" />{!item.is_read && <em className="sr-only">{t('Unread')}</em>}
              <span className="cx-notice-icon" aria-hidden="true"><Icon size={17} /></span>
              <span className="cx-notice-copy">
                <b>{notificationTitle(item)}</b>
                {noticeMessage(item) && <small>{noticeMessage(item)}</small>}
                <small className="cx-notice-meta">{joinParts(item.student_name, dateTimeText(item.created_at))}</small>
              </span>
              {target && <span className="cx-notice-action">{reviewItem ? t('Open in review') : t('Open item')}</span>}
            </button>
          </li>;
        })}
      </ul>}
      {chatsNext && <div className="paged-list-footer"><button type="button" className="button quiet small" onClick={moreChats} disabled={loadingChats} aria-busy={loadingChats}>{loadingChats ? t('Loading…') : t('Load more')}</button></div>}
      {firstPageLoading(list) && <p className="cx-empty" role="status">{t('Loading…')}</p>}
      <PagedListError list={list} />
      <LoadMore list={list} />
      {empty && <div className="cx-notices-empty"><span className="cx-logo" aria-hidden="true" /><p>{t('You are all caught up.')}</p></div>}
    </section>
  </div>;
}
