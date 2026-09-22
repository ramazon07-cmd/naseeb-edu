import { useEffect, useMemo, useRef, useState } from 'react';
import { Bookmark, X, Image, FileText, Link2, ExternalLink } from 'lucide-react';
import { api } from './api';
import { t } from './i18n';
import { collectSharedItems } from './chatSharedItems';

export default function ChatDetails({ channel, messages, onClose }) {
  const [tab, setTab] = useState('media');
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const closeRef = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const escape = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('keydown', escape); if (previous?.isConnected) previous.focus(); };
  }, []);
  useEffect(() => {
    let current = true;
    setLoading(true); setError('');
    api.list('channel-messages', `?channel=${encodeURIComponent(channel.id)}&page_size=100`).then((items) => {
      if (current) setHistory(items);
    }).catch((err) => { if (current) setError(err.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [channel.id, retry]);
  const items = useMemo(() => {
    const merged = new Map(history.map((message) => [message.id, message]));
    messages.forEach((message) => merged.set(message.id, message));
    return collectSharedItems([...merged.values()].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)));
  }, [history, messages]);
  const visible = items.filter((item) => item.kind === tab);
  const Icon = {media: Image, files: FileText, links: Link2}[tab];
  return <aside className="chat-details" aria-label={t('Contact info')}>
    <header><b>{t('Contact info')}</b><button ref={closeRef} type="button" className="icon-button" aria-label={t('Close contact info')} onClick={onClose}><X size={18} /></button></header>
    <div className="chat-contact"><span className="chat-contact-avatar">{channel.is_saved_messages ? <Bookmark size={28} /> : (channel.display_name || '?').charAt(0)}</span><h3>{channel.is_saved_messages ? t('Saved Messages') : channel.display_name}</h3><p>{channel.is_saved_messages ? t('Only you can see this') : channel.kind === 'direct' ? t('Direct conversation') : `${channel.members_count || 0} ${t('Members')}`}</p>{channel.description && <p>{channel.description}</p>}</div>
    <div className="chat-detail-tabs" role="tablist" aria-label={t('Shared content')}>{['media', 'files', 'links'].map((kind) => <button type="button" key={kind} role="tab" id={`shared-${kind}`} aria-controls="shared-content" aria-selected={kind === tab} onClick={() => setTab(kind)}>{t({media:'Media', files:'Files', links:'Links'}[kind])}<small>{items.filter((item) => item.kind === kind).length || ''}</small></button>)}</div>
    <div className="chat-shared-content" id="shared-content" role="tabpanel" aria-labelledby={`shared-${tab}`} aria-busy={loading}>
      {loading ? <p role="status">{t('Loading…')}</p> : error ? <div role="alert"><p>{error}</p><button className="button quiet small" onClick={() => setRetry((value) => value + 1)}>{t('Retry')}</button></div> : <><p className="shared-caption">{t('Links shared in this conversation')}</p>{visible.length ? visible.map((item) => <a key={item.url} href={item.url} target="_blank" rel="noopener noreferrer" className="chat-shared-item"><Icon size={20} /><span><b>{item.name}</b><small>{item.host}</small></span><ExternalLink size={13} /></a>) : <div className="chat-shared-empty"><Icon size={30} strokeWidth={1.3} /><p>{t({media:'No shared media yet.',files:'No shared files yet.',links:'No shared links yet.'}[tab])}</p></div>}</>}
    </div>
  </aside>;
}
