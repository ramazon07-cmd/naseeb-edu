import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowLeft, MessageCircle, UserRound, X } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { clockText, chatStampText, dateText } from '../lib/format';
import { counselorOf, markReadFor, unreadFor } from '../lib/counselorInbox';
import { restoredScrollTop, scrollAnchor } from '../lib/messageHistory';
import { announceNotificationsChanged } from '../lib/notifications';
import { InlineLoadError } from './states';

// Earlier counselor messages, oldest first, loaded a page at a time.
export function useCounselorInbox(enabled) {
  const [state, setState] = useState({ items: [], next: null, loaded: false, loading: false, error: '' });
  const busy = useRef(false);

  const load = useCallback(async (next = null) => {
    if (busy.current) return;
    busy.current = true;
    setState((current) => ({ ...current, loading: true, error: '' }));
    try {
      const page = await api.counselorMessages(next);
      const older = [...(page?.results || [])].reverse();
      setState((current) => {
        const seen = new Set(current.items.map((item) => item.id));
        const items = next ? [...older.filter((item) => !seen.has(item.id)), ...current.items] : older;
        return { items, next: page?.next || null, loaded: true, loading: false, error: '' };
      });
    } catch (err) {
      setState((current) => ({ ...current, loaded: true, loading: false, error: err.message }));
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);

  const markRead = useCallback((userId) => {
    setState((current) => ({ ...current, items: markReadFor(current.items, userId) }));
  }, []);

  return { ...state, reload: () => load(), loadOlder: () => state.next && load(state.next), markRead };
}

export function CounselorInboxItem({ inbox, user, active, onOpen }) {
  if (!inbox.items.length) return null;
  const latest = inbox.items[inbox.items.length - 1];
  const unread = unreadFor(inbox.items, user.id);
  return <button type="button" className={`channel-item counselor-inbox-item ${active ? 'active' : ''} ${unread ? 'unread' : ''}`} aria-current={active ? 'true' : undefined} onClick={onOpen}>
    <span className="avatar saved-avatar"><UserRound size={22} /></span>
    <span className="channel-item-copy"><span className="channel-item-top"><b>{t('From your counselor')}</b><time>{chatStampText(latest.created_at)}</time></span><span className="channel-item-bottom"><small>{latest.body}</small>{unread > 0 && <strong>{unread > 99 ? '99+' : unread}</strong>}</span></span>
  </button>;
}

// Read-only: these messages predate chats, so replies continue in a direct chat.
export function CounselorInboxThread({ inbox, user, onClose, onBack, onContinue }) {
  const listRef = useRef(null);
  const keepScroll = useRef(null);
  const [opening, setOpening] = useState(false);
  const unread = unreadFor(inbox.items, user.id);
  const counselorId = counselorOf(inbox.items, user.id);

  useEffect(() => {
    if (!unread) return;
    api.markCounselorMessagesRead().then(() => {
      inbox.markRead(user.id);
      announceNotificationsChanged();
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one write per batch of new messages
  }, [unread > 0, user.id]);

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (keepScroll.current != null) {
      list.scrollTop = restoredScrollTop(list, keepScroll.current);
      keepScroll.current = null;
    } else {
      list.scrollTop = list.scrollHeight;
    }
  }, [inbox.items.length]);

  function loadOlder() {
    keepScroll.current = scrollAnchor(listRef.current);
    inbox.loadOlder();
  }

  async function continueInChat() {
    if (!counselorId || opening) return;
    setOpening(true);
    try { await onContinue(counselorId); } finally { setOpening(false); }
  }

  return <section className="message-thread counselor-inbox">
    <header><div><button type="button" className="icon-button message-back" onClick={onBack} aria-label={t('Back to conversations')}><ArrowLeft size={18} /></button><span className="avatar saved-avatar"><UserRound size={22} /></span><div><b>{t('From your counselor')}</b><small>{t('Messages sent before chats were available')}</small></div></div><div className="channel-actions"><button type="button" className="icon-button close-chat" onClick={onClose} aria-label={t('Close chat')} title={t('Close chat')}><X size={18} /></button></div></header>
    <div className="message-list" ref={listRef} aria-busy={inbox.loading}>
      {inbox.error && <InlineLoadError message={inbox.error} onRetry={inbox.reload} />}
      {inbox.next && <div className="message-older"><button type="button" className="button quiet small" onClick={loadOlder} disabled={inbox.loading} aria-busy={inbox.loading}>{inbox.loading ? t('Loading…') : t('Load older messages')}</button></div>}
      {inbox.items.map((message, index) => {
        const mine = message.sender === user.id;
        const previous = inbox.items[index - 1];
        const newDay = !previous || new Date(previous.created_at).toDateString() !== new Date(message.created_at).toDateString();
        return <Fragment key={message.id}>
          {newDay && <div className="message-day"><span>{dateText(message.created_at)}</span></div>}
          <article className={`message-bubble ${mine ? 'mine' : ''}`}>
            <p>{message.body}<time>{clockText(message.created_at)}</time></p>
          </article>
        </Fragment>;
      })}
    </div>
    <footer className="counselor-inbox-footer">
      <p>{t('Replies to these messages now go through chat.')}</p>
      <button type="button" className="button primary small" onClick={continueInChat} disabled={!counselorId || opening} aria-busy={opening}><MessageCircle size={15} /> {opening ? t('Opening…') : t('Continue in chat')}</button>
    </footer>
  </section>;
}
