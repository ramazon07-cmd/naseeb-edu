import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ExternalLink, RefreshCw, Send, X } from 'lucide-react';
import { api } from '../api';
import { t } from '../i18n';
import { InlineLoadError } from './states';
import { DEFAULT_POST_HEIGHT, MAX_POST_HEIGHT, createHeightMemory, mergeTelegramPosts, skeletonShape, telegramEmbedUrl } from '../lib/telegramFeed';
import './telegramChannel.css';

// A post loads its frame once it has stayed near the viewport this long, so fast
// scrolling passes posts by without a download (videos in a post stream in full
// while its frame is alive). A post left behind is released after the second
// delay: that stops its downloads, and jitter at its edge does not reload it.
const LOAD_AFTER_MS = 200;
const RELEASE_AFTER_MS = 600;
// A frame that has not reported a size by then is not going to (blocked, offline).
const STALL_AFTER_MS = 12000;
const MAX_POST_WIDTH = 520;

const heights = createHeightMemory((() => { try { return window.sessionStorage; } catch { return null; } })());

// The width a post gets in the feed, whose side padding is fluid.
function postWidth(list) {
  const style = getComputedStyle(list);
  return Math.min(MAX_POST_WIDTH, list.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
}

// What a post that has not loaded looks like: the lines it will roughly have, at the height it will have.
function PostOutline({ post, height }) {
  const { media, lines } = skeletonShape(post, height);
  return <div className="telegram-skeleton-body" aria-hidden="true">
    {media && <i className="media" />}
    {lines.map((width, index) => <i key={index} style={{ '--w': `${width}%` }} />)}
  </div>;
}

function TelegramFeedSkeleton() {
  return <div className="telegram-feed-skeleton" role="status">
    {[3, 4].map((id) => <div key={id} className="telegram-post is-loading" style={{ height: 250 }}>
      <div className="telegram-post-skeleton"><PostOutline post={`naseeb_edu/${id}`} height={250} /></div>
    </div>)}
    <span className="sr-only">{t('Loading…')}</span>
  </div>;
}

const TelegramPost = memo(function TelegramPost({ post, dark, feed, width, above, onResize }) {
  const row = useRef(null);
  const frame = useRef(null);
  const instant = useRef(false);
  const [height, setHeight] = useState(() => heights.get(post, width.current) ?? DEFAULT_POST_HEIGHT);
  const measured = useRef(height);
  const [active, setActive] = useState(false);
  const [ready, setReady] = useState(false);
  const [stalled, setStalled] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const number = post.split('/')[1];
  // Native iframe lazy-loading preloads thousands of pixels ahead. Instead,
  // keep only nearby frames alive; preserve measured space when releasing one.
  useEffect(() => {
    let timer = 0;
    const observer = new IntersectionObserver(([entry]) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setActive(entry.isIntersecting), entry.isIntersecting ? LOAD_AFTER_MS : RELEASE_AFTER_MS);
    }, { root: feed.current, rootMargin: '32px 0px' });
    observer.observe(row.current);
    return () => { window.clearTimeout(timer); observer.disconnect(); };
  }, [feed]);
  useEffect(() => {
    setReady(false);
    setStalled(false);
    if (!active) return undefined;
    const stall = window.setTimeout(() => setStalled(true), STALL_AFTER_MS);
    const send = (event, data = {}) => frame.current?.contentWindow?.postMessage(JSON.stringify({ event, ...data }), 'https://t.me');
    function receive(event) {
      if (event.origin !== 'https://t.me' || event.source !== frame.current?.contentWindow) return;
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'ready') {
          send('focus', { has_focus: document.hasFocus() });
          send('visible');
        }
        if (data.event === 'resize' && Number.isFinite(Number(data.height)) && Number(data.height) > 0) {
          const next = Math.round(Math.min(MAX_POST_HEIGHT, Number(data.height)));
          window.clearTimeout(stall);
          heights.set(post, width.current, next);
          if (next !== measured.current) {
            // A post above what the reader looks at changes size at once and the list is kept in
            // place; every other post unfolds, with the feed staying put at the newest.
            instant.current = above(row.current);
            if (instant.current) row.current.style.transition = 'none';
            setHeight(next);
          }
          setReady(true);
        }
      } catch { /* Ignore unrelated widget messages. */ }
    }
    window.addEventListener('message', receive);
    return () => { window.clearTimeout(stall); window.removeEventListener('message', receive); };
  }, [active, dark, attempt, post, width, above]);
  useLayoutEffect(() => {
    const delta = height - measured.current;
    measured.current = height;
    if (!delta || !instant.current) return;
    onResize(delta);
    row.current.getBoundingClientRect(); // apply the new size before transitions come back
    row.current.style.transition = '';
    instant.current = false;
  }, [height, onResize]);
  const loading = active && !ready && !stalled;
  const failed = stalled && !ready;
  return <article ref={row} className={`telegram-post${ready ? ' is-ready' : ''}${loading ? ' is-loading' : ''}${failed ? ' is-stalled' : ''}`} style={{ height }} aria-busy={loading} aria-label={`${t('Telegram post')} ${number}`}>
    {active && <iframe key={`${dark ? 'dark' : 'light'}-${attempt}`} ref={frame}
      src={telegramEmbedUrl(post, dark)}
      title={`${t('Telegram post')} ${number}`} loading="lazy" allow="fullscreen" />}
    <div className="telegram-post-skeleton">
      <PostOutline post={post} height={height} />
      <footer>
        {failed ? <><span>{t('This post could not be loaded.')}</span><button type="button" className="button quiet small" onClick={() => setAttempt((count) => count + 1)}><RefreshCw size={13} /> {t('Retry')}</button></> : loading && <span className="sr-only">{t('Loading…')}</span>}
        <a href={`https://t.me/${post}`} target="_blank" rel="noopener noreferrer">{t('Open post in Telegram')} <ExternalLink size={13} /></a>
      </footer>
    </div>
  </article>;
});

export function TelegramChannel({ onClose }) {
  const [posts, setPosts] = useState([]);
  const [before, setBefore] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [failedCursor, setFailedCursor] = useState(null);
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark');
  const [atBottom, setAtBottom] = useState(true);
  const feed = useRef(null);
  const content = useRef(null);
  const width = useRef(MAX_POST_WIDTH);
  const pinned = useRef(true);
  const anchor = useRef(null);
  const alive = useRef(false);
  const busy = useRef(false);
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(document.documentElement.dataset.theme === 'dark'));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
  const jumpToLatest = useCallback(() => {
    pinned.current = true;
    setAtBottom(true);
    if (feed.current) feed.current.scrollTop = feed.current.scrollHeight;
  }, []);
  useEffect(() => {
    width.current = postWidth(feed.current);
    // The content changes size on every frame a post unfolds: stay with the newest through it.
    const observer = new ResizeObserver((entries) => {
      if (entries.some((entry) => entry.target === feed.current)) width.current = postWidth(feed.current);
      if (pinned.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight;
    });
    observer.observe(feed.current);
    observer.observe(content.current);
    return () => observer.disconnect();
  }, []);
  // Whether a post sits above what the reader looks at: the top of the viewport when
  // following the newest post, otherwise its middle. Its size changes must not move that.
  const above = useCallback((row) => {
    const list = feed.current;
    if (!list) return false;
    const view = list.getBoundingClientRect();
    return row.getBoundingClientRect().bottom <= (pinned.current ? view.top : view.top + view.height / 2);
  }, []);
  // A post above the reader changed size by `delta`: keep what the reader sees where it is.
  const onResize = useCallback((delta) => {
    const list = feed.current;
    if (!list) return;
    if (pinned.current) list.scrollTop = list.scrollHeight;
    else list.scrollTop += delta;
  }, []);
  const load = useCallback(async (cursor = null) => {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError('');
    try {
      const data = await api.telegramFeed(cursor);
      if (!alive.current) return;
      const list = feed.current;
      // Capture immediately before the prepend, allowing scrolling during fetch.
      anchor.current = cursor && list ? list.scrollHeight - list.scrollTop : null;
      if (!cursor) pinned.current = true;
      setPosts((current) => mergeTelegramPosts(cursor ? current : [], data.posts || []));
      setBefore(data.before);
    } catch {
      if (alive.current) {
        setError(t('Telegram posts could not be loaded. Please retry.'));
        setFailedCursor(cursor);
      }
    } finally {
      busy.current = false;
      if (alive.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    load();
    return () => { alive.current = false; };
  }, [load]);
  useLayoutEffect(() => {
    const list = feed.current;
    if (!list) return;
    if (anchor.current !== null) {
      list.scrollTop = list.scrollHeight - anchor.current;
      anchor.current = null;
    } else if (pinned.current) jumpToLatest();
  }, [posts, jumpToLatest]);
  return <section className="message-thread telegram-channel">
    <header><div>
      <button type="button" className="icon-button message-back" onClick={onClose} aria-label={t('Back to conversations')}><ArrowLeft size={18} /></button>
      <span className="avatar saved-avatar"><Send size={22} /></span>
      <div><b>{t('Naseeb Edu')}</b><small>{t('Official Telegram channel')}</small></div>
    </div><div className="channel-actions">
      <button type="button" className="icon-button" onClick={() => load()} disabled={loading} aria-label={t('Refresh posts')} title={t('Refresh posts')}><RefreshCw size={18} /></button>
      <a className="icon-button" href="https://t.me/naseeb_edu" target="_blank" rel="noopener noreferrer" aria-label={t('Open in Telegram')} title={t('Open in Telegram')}><ExternalLink size={18} /></a>
      <button type="button" className="icon-button close-chat" onClick={onClose} aria-label={t('Close chat')} title={t('Close chat')}><X size={18} /></button>
    </div></header>
    <div className="telegram-feed-wrap">
      <div className="telegram-feed" ref={feed} aria-busy={loading} onScroll={() => {
        const list = feed.current;
        pinned.current = list.scrollHeight - list.scrollTop - list.clientHeight < 48;
        setAtBottom(pinned.current);
      }}>
        <div className="telegram-feed-content" ref={content}>
          {before && <button type="button" className="button quiet telegram-older" disabled={loading} onClick={() => load(before)}>{loading ? t('Loading…') : t('Load older posts')}</button>}
          {error && <InlineLoadError message={error} onRetry={() => load(failedCursor)} />}
          {loading && !posts.length && <TelegramFeedSkeleton />}
          {posts.map((post) => <TelegramPost key={post} post={post} dark={dark} feed={feed} width={width} above={above} onResize={onResize} />)}
          {!loading && !error && !posts.length && <p className="telegram-empty">{t('No channel posts yet.')}</p>}
        </div>
      </div>
      {!atBottom && posts.length > 0 && <button type="button" className="telegram-jump icon-button" onClick={jumpToLatest} title={t('Latest post')} aria-label={t('Latest post')}><ArrowDown size={20} /></button>}
    </div>
    <footer className="telegram-channel-footer"><Send size={13} /><span>{t('Official Telegram channel')}</span><a href="https://t.me/naseeb_edu" target="_blank" rel="noopener noreferrer">{t('Open in Telegram')} <ExternalLink size={12} /></a></footer>
  </section>;
}
