import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, Lock, MessageSquare } from 'lucide-react';
import '@fontsource-variable/newsreader/wght.css';
import { api } from '../api';
import { t, tp, tx } from '../i18n';
import { CxTag } from '../components/counselorUi';
import { PageSkeleton } from '../components/states';
import { invalidatePagedLists } from '../hooks/usePagedList';
import { ESSAY_STATUS_TONE, accessLevel, blockId, isTextBlock, orderedThreads, safeHref, textBetween } from '../lib/essayReview';
import { dateTimeText, joinParts } from '../lib/format';
import { label } from '../lib/labels';
import './counselor-essay-review.css';

const POLL_MS = 20_000;
const ACCESS_TEXT = { suggest: 'Comments and suggestions', comment: 'Comments only', view: 'View only' };

// -- the document -------------------------------------------------------------
// Offsets must match the server's (lib/essayReview.js): every text node is wrapped in
// a span carrying the offset where it starts, so a selection can be turned back into
// (paragraph id, start, end).

function wrapMarks(node, marks, ctx, key) {
  return (marks || []).reduce((inner, mark, index) => {
    const id = mark.attrs?.id;
    const k = `${key}-${index}`;
    switch (mark.type) {
      case 'bold': return <strong key={k}>{inner}</strong>;
      case 'italic': return <em key={k}>{inner}</em>;
      case 'underline': return <u key={k}>{inner}</u>;
      case 'strike': return <s key={k}>{inner}</s>;
      case 'highlight': return <mark key={k}>{inner}</mark>;
      case 'link': return safeHref(mark.attrs?.href) ? <a key={k} href={mark.attrs.href} target="_blank" rel="noopener noreferrer">{inner}</a> : inner;
      case 'comment': {
        const classes = `cer-comment${ctx.active === id ? ' is-active' : ''}`;
        return <span key={k} className={classes} data-thread={id} onClick={() => ctx.onPick(id)}>{inner}</span>;
      }
      case 'suggestInsert': return <ins key={k} className="cer-ins">{inner}</ins>;
      case 'suggestDelete': return <del key={k} className="cer-del">{inner}</del>;
      default: return inner;
    }
  }, node);
}

function renderLeaf(leaf, ctx) {
  if (ctx.leaves++) ctx.pos += 1;
  const items = [];
  (leaf.content || []).forEach((child, index) => {
    if (child.type === 'text') {
      const start = ctx.pos;
      ctx.pos += child.text.length;
      items.push(wrapMarks(<span key={index} data-s={start}>{child.text}</span>, child.marks, ctx, index));
    } else {
      items.push(<br key={index} data-s={ctx.pos} />);
      ctx.pos += 1;
    }
  });
  if (!items.length) items.push(<br key="empty" />);
  return items;
}

function renderNode(node, ctx, key) {
  const style = { textAlign: node.attrs?.textAlign || undefined, lineHeight: node.attrs?.lineHeight || undefined, marginLeft: node.attrs?.indent ? `${node.attrs.indent * 2}em` : undefined };
  switch (node.type) {
    case 'paragraph': return <p key={key} style={style}>{renderLeaf(node, ctx)}</p>;
    case 'title': return <h2 key={key} className="cer-title" style={style}>{renderLeaf(node, ctx)}</h2>;
    case 'subtitle': return <p key={key} className="cer-subtitle" style={style}>{renderLeaf(node, ctx)}</p>;
    case 'heading': return <h3 key={key} className={`cer-h${node.attrs?.level || 1}`} style={style}>{renderLeaf(node, ctx)}</h3>;
    case 'bulletList': return <ul key={key}>{(node.content || []).map((child, index) => renderNode(child, ctx, index))}</ul>;
    case 'orderedList': return <ol key={key}>{(node.content || []).map((child, index) => renderNode(child, ctx, index))}</ol>;
    case 'listItem': return <li key={key}>{(node.content || []).map((child, index) => renderNode(child, ctx, index))}</li>;
    case 'blockquote': return <blockquote key={key}>{(node.content || []).map((child, index) => renderNode(child, ctx, index))}</blockquote>;
    case 'pageBreak': return <hr key={key} className="cer-break" />;
    default: return isTextBlock(node) ? <p key={key}>{renderLeaf(node, ctx)}</p> : null;
  }
}

function DocView({ doc, threads, active, onPick, rootRef }) {
  const byId = useMemo(() => new Map(threads.map((thread) => [thread.id, thread])), [threads]);
  return <div className="cer-doc" ref={rootRef}>
    {(doc?.content || []).map((block, index) => {
      const ctx = { pos: 0, leaves: 0, threads: byId, active, onPick };
      return <div key={blockId(block) || index} className="cer-block" data-bid={blockId(block)}>{renderNode(block, ctx, 0)}</div>;
    })}
  </div>;
}

// -- selection -> (paragraph, start, end) -----------------------------------------

function textEnd(span) {
  return Number(span.dataset.s) + (span.tagName === 'BR' ? 1 : span.textContent.length);
}

// The offset a range boundary stands for: inside a text span, or the nearest text before/after it.
function boundary(root, node, offset, isEnd) {
  if (node.nodeType === 3) {
    const span = node.parentElement?.closest('[data-s]');
    if (!span || !root.contains(span)) return null;
    return { bid: span.closest('[data-bid]')?.dataset.bid, at: Number(span.dataset.s) + offset };
  }
  const children = [...node.childNodes];
  const side = isEnd ? children.slice(0, offset).reverse() : children.slice(offset);
  for (const child of side) {
    if (child.nodeType !== 1) continue;
    const spans = child.matches('[data-s]') ? [child] : [...child.querySelectorAll('[data-s]')];
    if (!spans.length) continue;
    const span = isEnd ? spans.at(-1) : spans[0];
    return { bid: span.closest('[data-bid]')?.dataset.bid, at: isEnd ? textEnd(span) : Number(span.dataset.s) };
  }
  if (node === root || !node.parentNode) return null;
  const index = [...node.parentNode.childNodes].indexOf(node);
  return boundary(root, node.parentNode, isEnd ? index : index + 1, isEnd);
}

function lastOffsetOf(root, bid) {
  const spans = [...root.querySelectorAll(`[data-bid="${CSS.escape(bid)}"] [data-s]`)];
  return spans.length ? textEnd(spans.at(-1)) : 0;
}

// -- the page ------------------------------------------------------------------

function Comment({ comment }) {
  return <div className="cer-comment-row"><b>{comment.by_me ? t('You') : comment.author_name}</b><time>{dateTimeText(comment.created_at)}</time><p>{comment.body}</p></div>;
}

function Thread({ thread, active, canComment, onPick, onReply, busy }) {
  const [replying, setReplying] = useState(false);
  const [body, setBody] = useState('');
  async function send(event) {
    event.preventDefault();
    if (!canComment || busy || !body.trim()) return;
    if (await onReply(thread, body.trim())) { setBody(''); setReplying(false); }
  }
  return <article className={`cer-thread${active ? ' is-active' : ''}`} data-thread-card={thread.id}>
    <button type="button" className="cer-quote" onClick={() => onPick(thread.id)}>{thread.quote ? `“${thread.quote}”` : t('Comment')}</button>
    {thread.comments.map((comment) => <Comment key={comment.id} comment={comment} />)}
    {canComment && !replying && <div className="cer-thread-actions">
      <button type="button" disabled={busy} className="cx-btn" onClick={() => setReplying(true)}>{t('Add comment')}</button>
    </div>}
    {replying && canComment && <form className="cer-reply" onSubmit={send}>
      <textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={2000} rows={2} aria-label={t('Add comment')} placeholder={t('Write your comment')} autoFocus />
      <div className="cer-thread-actions"><button type="button" className="cx-btn" onClick={() => { setReplying(false); setBody(''); }}>{t('Cancel')}</button><button className="cx-btn primary" disabled={busy || !body.trim()}>{t('Add comment')}</button></div>
    </form>}
  </article>;
}

export function CounselorEssayReview({ essayId, notify, reload, onBack }) {
  const [review, setReview] = useState(null);
  const [record, setRecord] = useState(null);
  const [phase, setPhase] = useState('loading');
  const [selection, setSelection] = useState(null);
  const [mode, setMode] = useState('comment');
  const [draft, setDraft] = useState('');
  const [active, setActive] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const docRef = useRef(null);
  const shown = useRef('');
  const tabRef = useRef(null);
  const level = accessLevel(review?.capabilities);
  const approved = (review?.status ?? record?.status) === 'approved';
  const canComment = !approved && level !== 'view';
  const canSuggest = !approved && level === 'suggest';

  // `silent` refreshes in the background: nothing changes on screen unless the essay did.
  const load = useCallback(async ({ tab = tabRef.current, silent = false } = {}) => {
    try {
      const [next, rec] = await Promise.all([api.reviewEssay(essayId, tab), silent ? null : api.retrieve('essays', essayId)]);
      const signature = JSON.stringify([next.tab, next.threads, next.suggestions, next.capabilities, next.status]);
      if (!silent || signature !== shown.current) { shown.current = signature; setReview(next); }
      tabRef.current = next.tab.id;
      if (rec) setRecord(rec);
      setPhase('ready');
    } catch (err) {
      if (!silent) setPhase(err?.status === 404 ? 'missing' : 'error');
    }
  }, [essayId]);

  useEffect(() => { tabRef.current = null; shown.current = ''; setPhase('loading'); load({ tab: null }); }, [essayId, load]);

  // Keep permissions current even while a reply or review note is being written.
  useEffect(() => {
    if (phase !== 'ready') return undefined;
    const timer = setInterval(() => { if (document.visibilityState === 'visible') load({ silent: true }); }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase, load]);

  // What the counselor selected in the text. A selection made elsewhere (the side panel) is ignored, so it stays while they type.
  useEffect(() => {
    function onChange() {
      const root = docRef.current;
      const sel = window.getSelection();
      if (!root || !sel?.rangeCount) return;
      const range = sel.getRangeAt(0);
      if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return;
      const from = boundary(root, range.startContainer, range.startOffset, false);
      let to = boundary(root, range.endContainer, range.endOffset, true);
      if (!from?.bid || !to?.bid) return;
      // A comment lives in one paragraph: a longer selection is cut at the end of its first.
      if (to.bid !== from.bid) to = { bid: from.bid, at: lastOffsetOf(root, from.bid) };
      const start = Math.min(from.at, to.at);
      const end = Math.max(from.at, to.at);
      const block = review?.tab?.doc?.content?.find((item) => blockId(item) === from.bid);
      setSelection({ bid: from.bid, start, end, text: block ? textBetween(block, start, end) : '' });
    }
    document.addEventListener('selectionchange', onChange);
    return () => document.removeEventListener('selectionchange', onChange);
  }, [review]);

  const threads = review?.threads || [];
  const comments = useMemo(() => orderedThreads(threads), [threads]);

  function pick(id) {
    setActive(id);
    document.querySelector(`[data-thread-card="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function clearSelection() {
    window.getSelection()?.removeAllRanges();
    setSelection(null);
    setDraft('');
  }

  async function guarded(action) {
    setBusy(true);
    try {
      await action();
      return true;
    } catch (err) {
      notify(err.message, 'error');
      load({ silent: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submitFeedback(event) {
    event.preventDefault();
    if (!canComment || busy || !selection) return;
    const { bid, start, end } = selection;
    const tab = review.tab.id;
    const done = await guarded(async () => {
      if (mode === 'comment') {
        await api.reviewEssayThread(essayId, { tab, bid, start, end, body: draft.trim() });
        notify(t('Comment added.'));
      } else {
        await api.reviewEssaySuggest(essayId, { tab, items: [{ bid, start, end, text: draft }] });
        notify(t('Suggestion sent.'));
      }
      await load({ silent: true });
    });
    if (done) clearSelection();
  }

  const reply = (thread, body) => guarded(async () => { await api.reviewEssayReply(essayId, thread.id, body); await load({ silent: true }); });

  async function decide(action) {
    const text = note.trim();
    if (action === 'sendBack' && !text) {
      notify(t('Add a note explaining what needs to change.'), 'error');
      document.getElementById('cer-decision-note')?.focus();
      return;
    }
    const status = action === 'approve' ? 'approved' : 'needs_revision';
    const payload = {};
    if (record.status !== status) payload.status = status;
    if (text && text !== record.counselor_comment) payload.counselor_comment = text;
    const done = await guarded(async () => {
      if (Object.keys(payload).length) await api.update('essays', essayId, payload);
      notify(action === 'approve' ? t('Essay approved.') : t('Sent back to the student.'));
    });
    if (done) {
      invalidatePagedLists(['essays']);
      reload?.();
      onBack();
    }
  }

  const back = <button type="button" className="cx-back" onClick={onBack}><ChevronLeft size={16} aria-hidden="true" /><b>{t('Essays')}</b></button>;
  if (phase === 'loading') return <div className="cx-page cer-page">{back}<PageSkeleton /></div>;
  if (phase !== 'ready') {
    return <div className="cx-page cer-page">{back}<div className="cx-card cer-gone" role={phase === 'error' ? 'alert' : 'status'}>
      <Lock size={20} aria-hidden="true" />
      <p>{phase === 'missing' ? t('This essay is not available. The student may have stopped sharing it.') : t('The essay could not be loaded.')}</p>
      <button type="button" className="cx-btn" onClick={() => { setPhase('loading'); load(); }}>{t('Retry')}</button>
    </div></div>;
  }

  const tab = review.tab;
  const tabMeta = review.tabs.find((item) => item.id === tab.id);
  const words = tabMeta?.word_count ?? 0;
  const hasSelection = Boolean(selection);
  const range = hasSelection && selection.end > selection.start;
  const canSubmit = hasSelection && draft.trim() && (mode === 'suggest' ? true : range);
  return <div className="cx-page cer-page">
    <div className="cer-top">{back}<span className="cx-crumb">/ {review.student_name}</span></div>
    <header className="cer-head">
      <div>
        <h1>{review.title}</h1>
        <p>{joinParts(review.student_name, record?.university_name || t('General essay'), record && tx`Version ${record.version}`, tp('{n} word|{n} words', words, { n: words }))}</p>
      </div>
      <div className="cer-head-tags">
        {record && <CxTag tone={ESSAY_STATUS_TONE[review.status ?? record.status] || 'quiet'}>{label(review.status ?? record.status)}</CxTag>}
        <span className={`cer-access is-${level}`}>{level === 'view' && <Lock size={13} aria-hidden="true" />}{t(ACCESS_TEXT[level])}</span>
      </div>
    </header>
    {review.prompt && <section className="cer-prompt"><span>{t('Essay prompt')}</span><p>{review.prompt}</p></section>}
    {review.tabs.length > 1 && <div className="cer-tabs" role="tablist" aria-label={t('Essay tabs')}>
      {review.tabs.map((item) => <button key={item.id} type="button" role="tab" aria-selected={item.id === tab.id} className={item.id === tab.id ? 'active' : ''} onClick={() => { clearSelection(); load({ tab: item.id }); }}>{item.title || t('Untitled')}</button>)}
    </div>}

    <div className="cer-layout">
      <article className="cer-paper" aria-label={t('Essay text')}><DocView doc={tab.doc} threads={threads} active={active} onPick={pick} rootRef={docRef} /></article>
      <aside className="cer-side" aria-label={t('Feedback')}>
        {!approved && <section className="cer-card">
          <h2>{t('Your feedback')}</h2>
          {!canComment && <p className="cer-hint"><Lock size={14} aria-hidden="true" /> {t('The student has not allowed comments on this essay.')}</p>}
          {canComment && !hasSelection && <p className="cer-hint"><MessageSquare size={14} aria-hidden="true" /> {t('Select words in the essay to comment or suggest a change.')}</p>}
          {canComment && hasSelection && <form className="cer-compose" onSubmit={submitFeedback}>
            {selection.text ? <blockquote>{`“${selection.text.length > 160 ? `${selection.text.slice(0, 160)}…` : selection.text}”`}</blockquote> : <p className="cer-hint">{t('A spot in the text')}</p>}
            {canSuggest && <div className="cer-modes" role="group" aria-label={t('Kind of feedback')}>
              <button type="button" aria-pressed={mode === 'comment'} onClick={() => setMode('comment')}>{t('Comment')}</button>
              <button type="button" aria-pressed={mode === 'suggest'} onClick={() => setMode('suggest')}>{t('Suggest a change')}</button>
            </div>}
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={2000} rows={3}
              placeholder={mode === 'suggest' ? t('The new words (leave empty to suggest removing the selection)') : t('Write your comment')} aria-label={mode === 'suggest' ? t('Suggested text') : t('Comment')} />
            {mode === 'comment' && !range && <p className="cer-hint">{t('Select some words to comment on.')}</p>}
            <div className="cer-thread-actions">
              <button type="button" className="cx-btn" onClick={clearSelection}>{t('Cancel')}</button>
              <button className="cx-btn primary" disabled={busy || (mode === 'comment' ? !canSubmit : !(range || draft))} aria-busy={busy}>{mode === 'suggest' ? t('Suggest') : t('Comment')}</button>
            </div>
          </form>}
        </section>}

        <section className="cer-card">
          <h2>{tp('{n} comment|{n} comments', comments.length, { n: comments.length })}</h2>
          {!comments.length && <p className="cer-hint">{t('No comments yet.')}</p>}
          {comments.map((thread) => <Thread key={thread.id} thread={thread} active={active === thread.id} canComment={canComment} onPick={pick} onReply={reply} busy={busy} />)}
        </section>

        {review.suggestions.length > 0 && <section className="cer-card">
          <h2>{tp('{n} suggested change|{n} suggested changes', review.suggestions.length, { n: review.suggestions.length })}</h2>
          <p className="cer-hint">{t('The student accepts or rejects each one.')}</p>
          {review.suggestions.map((item) => <div key={item.id} className="cer-suggestion">
            {item.delete_text && <del>{item.delete_text}</del>}
            {item.insert_text && <ins>{item.insert_text}</ins>}
            <small>{joinParts(item.by_me ? t('You') : item.author_name, dateTimeText(item.created_at))}</small>
          </div>)}
        </section>}
      </aside>
    </div>

    <section className="cer-decide" aria-label={t('Your decision')}>
      {approved ? <p className="cer-approved">{t('This essay is approved.')}</p> : <>
        <label htmlFor="cer-decision-note">{t('Note to the student (optional for approve, required to send back)')}</label>
        <textarea id="cer-decision-note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={2} placeholder={record?.counselor_comment || ''} />
        <div className="cer-decide-actions">
          <button type="button" className="cx-btn" disabled={busy} onClick={() => decide('sendBack')}>{t('Send back with note')}</button>
          <button type="button" className="cx-btn primary" disabled={busy} aria-busy={busy} onClick={() => decide('approve')}>{t('Approve')}</button>
        </div>
      </>}
    </section>
  </div>;
}
