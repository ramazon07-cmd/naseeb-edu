import { memo, useState } from 'react'
import { Check, CheckCheck, MessageSquare, RotateCcw, X } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { relativeTime } from './format.js'

const who = (item) => (item.by_me ? t('You') : item.author_name || t('Your counselor'))

function Meta({ item }) {
  return <span className="el-fb-meta"><strong>{who(item)}</strong> · {relativeTime(item.created_at) || ''}</span>
}

function SuggestionCard({ item, active, busy, onSelect, onDecide }) {
  const { delete_text: removed, insert_text: added } = item
  let summary
  if (removed && added) summary = <>{t('Replace')} <del className="el-suggest-del">{removed}</del> {t('with')} <ins className="el-suggest-ins">{added}</ins></>
  else if (added) summary = <>{t('Add')} <ins className="el-suggest-ins">{added}</ins></>
  else summary = <>{t('Delete')} <del className="el-suggest-del">{removed}</del></>
  return <li className={`el-fb-card is-suggestion${active ? ' is-active' : ''}`}>
    <button type="button" className="el-fb-select" onClick={() => onSelect(item)} aria-pressed={active}
      aria-label={t('Show this suggestion in the text')}>
      <Meta item={item} />
      <span className="el-fb-kind">{t('Suggested edit')}</span>
      <span className="el-fb-summary">{summary}</span>
    </button>
    {!item.anchored && <p className="el-fb-note">{t('The words this suggestion was about have changed. You can still reject it.')}</p>}
    <div className="el-fb-actions">
      <button type="button" className="el-btn is-small is-primary el-fb-btn" disabled={busy || !item.anchored} aria-busy={busy}
        onClick={() => onDecide([{ id: item.id, accept: true }])}><Check size={16} aria-hidden="true" />{t('Accept')}</button>
      <button type="button" className="el-btn is-small el-fb-btn" disabled={busy} onClick={() => onDecide([{ id: item.id, accept: false }])}>
        <X size={16} aria-hidden="true" />{t('Reject')}</button>
    </div>
  </li>
}

function ThreadCard({ item, active, busy, onSelect, onReply, onResolve, onReopen }) {
  const [replying, setReplying] = useState(false)
  const [body, setBody] = useState('')
  const resolved = item.status === 'resolved'
  async function send(event) {
    event.preventDefault()
    const text = body.trim()
    if (!text) return
    if (await onReply(item, text)) { setBody(''); setReplying(false) }
  }
  const [first, ...replies] = item.comments || []
  return <li className={`el-fb-card is-thread${active ? ' is-active' : ''}${resolved ? ' is-resolved' : ''}`}>
    <button type="button" className="el-fb-select" onClick={() => onSelect(item)} aria-pressed={active} aria-label={t('Show this comment in the text')}>
      <Meta item={first || item} />
      {item.quote && <span className={`el-fb-quote${item.anchored ? '' : ' is-gone'}`}>“{item.quote}”</span>}
      {!item.anchored && <span className="el-fb-note">{t('The highlighted words were changed or removed.')}</span>}
      {first && <span className="el-fb-body">{first.body}</span>}
    </button>
    {replies.length > 0 && <ul className="el-fb-replies">{replies.map((comment) => <li key={comment.id}>
      <Meta item={comment} />
      <p className="el-fb-body">{comment.body}</p>
    </li>)}</ul>}
    {replying && <form className="el-fb-reply" onSubmit={send}>
      <label className="el-sr-only" htmlFor={`el-reply-${item.id}`}>{t('Reply')}</label>
      <textarea id={`el-reply-${item.id}`} className="el-input" rows={2} maxLength={2000} autoFocus value={body}
        placeholder={t('Write a reply…')} onChange={(event) => setBody(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Escape') setReplying(false) }} />
      <div className="el-fb-actions">
        <button type="submit" className="el-btn is-small is-primary el-fb-btn" disabled={busy || !body.trim()} aria-busy={busy}>{t('Send')}</button>
        <button type="button" className="el-btn is-small el-fb-btn" onClick={() => setReplying(false)}>{t('Cancel')}</button>
      </div>
    </form>}
    {!replying && <div className="el-fb-actions">
      {!resolved && <button type="button" className="el-btn is-small el-fb-btn" onClick={() => setReplying(true)}><MessageSquare size={15} aria-hidden="true" />{t('Reply')}</button>}
      {resolved
        ? <button type="button" className="el-btn is-small el-fb-btn" disabled={busy} onClick={() => onReopen(item)}><RotateCcw size={15} aria-hidden="true" />{t('Reopen')}</button>
        : <button type="button" className="el-btn is-small el-fb-btn" disabled={busy} onClick={() => onResolve(item)}><Check size={15} aria-hidden="true" />{t('Resolve')}</button>}
    </div>}
  </li>
}

// Counselor feedback on the open tab: suggested edits and comment threads in
// the order of the text. A side panel on wide screens, a bottom sheet on phones.
function CommentsPanel({ items, activeKey, busyKey, acceptAll, loaded, error, onSelect, onDecide, onReply, onResolve, onReopen, onRetry, onClose }) {
  const [showResolved, setShowResolved] = useState(false)
  const { open, resolved } = items
  const card = (item) => {
    const key = `${item.kind}:${item.id}`
    const props = { item, active: key === activeKey, busy: busyKey === key || busyKey === 'all', onSelect }
    return item.kind === 'suggestion'
      ? <SuggestionCard key={key} {...props} onDecide={onDecide} />
      : <ThreadCard key={key} {...props} onReply={onReply} onResolve={onResolve} onReopen={onReopen} />
  }
  return <aside className="el-side-panel el-comments" aria-label={t('Comments and suggestions')}>
    <div className="el-history-head">
      <MessageSquare size={18} aria-hidden="true" />
      <strong>{t('Comments · {n}', { n: open.length })}</strong>
      <button type="button" className="el-icon-btn" aria-label={t('Close comments')} title={t('Close')} onClick={onClose}><X size={18} /></button>
    </div>
    <div className="el-history-body el-fb-body-list">
      {acceptAll.length > 1 && <button type="button" className="el-btn is-primary el-fb-all" disabled={busyKey === 'all'} aria-busy={busyKey === 'all'}
        onClick={() => onDecide(acceptAll.map((id) => ({ id, accept: true })), 'all')}>
        <CheckCheck size={17} aria-hidden="true" />{tp('Accept all {n} suggestions', acceptAll.length, { n: acceptAll.length })}
      </button>}
      {error && <div className="el-alert is-error" role="alert"><span>{error}</span><button type="button" className="el-btn is-small" onClick={onRetry}>{t('Retry')}</button></div>}
      {!loaded && !error && <p className="el-small" role="status">{t('Loading…')}</p>}
      {loaded && !open.length && <p className="el-small">{t('No open comments. When your counselor comments on this essay or suggests an edit, it shows up here.')}</p>}
      <ul className="el-fb-list">{open.map(card)}</ul>
      {resolved.length > 0 && <>
        <button type="button" className="el-link el-fb-toggle" aria-expanded={showResolved} onClick={() => setShowResolved((value) => !value)}>
          {showResolved ? t('Hide resolved') : tp('Show resolved ({n})', resolved.length, { n: resolved.length })}
        </button>
        {showResolved && <ul className="el-fb-list">{resolved.map(card)}</ul>}
      </>}
    </div>
  </aside>
}

export default memo(CommentsPanel)
