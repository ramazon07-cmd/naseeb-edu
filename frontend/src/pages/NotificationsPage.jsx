import { useCallback, useEffect, useState } from 'react';
import { Bell, CheckCheck, MessageCircle } from 'lucide-react';
import { api } from '../api';
import { formatNumberLocale, t } from '../i18n';
import { dateTimeText, joinParts } from '../lib/format';
import { NOTIFICATIONS_CHANGED, reviewItemForNotice } from '../lib/notifications';
import { notificationTitle } from '../lib/notificationText';
import { KIND_ICONS, noticeMessage, useNotificationFeed } from '../components/NotificationPanel';
import { LoadMore, PagedListError, firstPageLoading } from '../components/paged';
import { CxHead } from '../components/counselorUi';
import { invalidatePagedLists } from '../hooks/usePagedList';

// The counselor's full notification list ("What happened since your last
// visit"): unread chats first, then the notices addressed to them, newest
// first, a page at a time. The bell's panel is the short version of this.
export function NotificationsPage({ notify, setPage }) {
  const [summary, setSummary] = useState(null);
  const loadSummary = useCallback(() => api.notificationSummary().then(setSummary).catch(() => {}), []);
  useEffect(() => {
    loadSummary();
    window.addEventListener(NOTIFICATIONS_CHANGED, loadSummary);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, loadSummary);
  }, [loadSummary]);
  const feed = useNotificationFeed({ summary, notify, staff: true });
  const { list, chats, chatsNext, loadingChats, moreChats, markAll, markingAll, empty } = feed;
  // Notices read here must not come back unread from the page cache (Back, the bell).
  useEffect(() => () => invalidatePagedLists(['notifications']), []);

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
