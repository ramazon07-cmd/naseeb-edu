import { memo, useState } from 'react'
import { Check, CheckCheck, MessageSquare, X } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { relativeTime, whenWritten } from './format.js'

const who = (item) => (item.by_me ? t('You') : item.author_name || t('Your counselor'))

function Meta({ item }) {
  const when = relativeTime(item.created_at)
  return <span className="el-fb-meta">
    <strong>{who(item)}</strong>
    {when && <time dateTime={item.created_at} title={whenWritten(item.created_at)}>{when}</time>}
  </span>
}

function SuggestionCard({ item, active, busy, readOnly, onSelect, onDecide }) {
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
    {!item.anchored && !readOnly && <p className="el-fb-note">{t('The words this suggestion was about have changed. You can still reject it.')}</p>}
    {!readOnly && <div className="el-fb-actions">
      <button type="button" className="el-btn is-small is-primary el-fb-btn" disabled={busy || !item.anchored} aria-busy={busy}
        onClick={() => onDecide([{ id: item.id, accept: true }])}><Check size={16} aria-hidden="true" />{t('Accept')}</button>
      <button type="button" className="el-btn is-small el-fb-btn" disabled={busy} onClick={() => onDecide([{ id: item.id, accept: false }])}>
        <X size={16} aria-hidden="true" />{t('Reject')}</button>
    </div>}
  </li>
}

function ThreadCard({ item, active, busy, readOnly, onSelect, onReply }) {
  const [replying, setReplying] = useState(false)
  const [body, setBody] = useState('')
  async function send(event) {
    event.preventDefault()
    const text = body.trim()
    if (readOnly || busy || !text) return
    if (await onReply(item, text)) { setBody(''); setReplying(false) }
  }
  const [first, ...replies] = item.comments || []
  return <li className={`el-fb-card is-thread${active ? ' is-active' : ''}`}>
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
    {!readOnly && replying && <form className="el-fb-reply" onSubmit={send}>
      <label className="el-sr-only" htmlFor={`el-reply-${item.id}`}>{t('Add comment')}</label>
      <textarea id={`el-reply-${item.id}`} className="el-input" rows={2} maxLength={2000} autoFocus value={body}
        placeholder={t('Write your comment')} onChange={(event) => setBody(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Escape') setReplying(false) }} />
      <div className="el-fb-actions">
        <button type="submit" className="el-btn is-small is-primary el-fb-btn" disabled={busy || !body.trim()} aria-busy={busy}>{t('Add comment')}</button>
        <button type="button" className="el-btn is-small el-fb-btn" onClick={() => setReplying(false)}>{t('Cancel')}</button>
      </div>
    </form>}
    {!readOnly && !replying && <div className="el-fb-actions">
      <button type="button" className="el-btn is-small el-fb-btn" disabled={busy} onClick={() => setReplying(true)}><MessageSquare size={15} aria-hidden="true" />{t('Add comment')}</button>
    </div>}
  </li>
}

// Counselor feedback on the open tab: suggested edits and comment threads in
// the order of the text. A side panel on wide screens, a bottom sheet on phones.
function CommentsPanel({ readOnly = false, items, activeKey, busyKey, acceptAll, loaded, error, onSelect, onDecide, onReply, onRetry, onClose }) {
  const card = (item) => {
    const key = `${item.kind}:${item.id}`
    const props = { item, active: key === activeKey, busy: busyKey === key || busyKey === 'all', readOnly, onSelect }
    return item.kind === 'suggestion'
      ? <SuggestionCard key={key} {...props} onDecide={onDecide} />
      : <ThreadCard key={key} {...props} onReply={onReply} />
  }
  return <aside className="el-side-panel el-comments" aria-label={t('Comments and suggestions')}>
    <div className="el-history-head">
      <MessageSquare size={18} aria-hidden="true" />
      <strong>{t('Comments · {n}', { n: items.length })}</strong>
      <button type="button" className="el-icon-btn" aria-label={t('Close comments')} title={t('Close')} onClick={onClose}><X size={18} /></button>
    </div>
    <div className="el-history-body el-fb-body-list">
      {readOnly && <p className="el-small" role="status">{t('This essay is approved. Feedback is read-only.')}</p>}
      {!readOnly && acceptAll.length > 1 && <button type="button" className="el-btn is-primary el-fb-all" disabled={busyKey === 'all'} aria-busy={busyKey === 'all'}
        onClick={() => onDecide(acceptAll.map((id) => ({ id, accept: true })), 'all')}>
        <CheckCheck size={17} aria-hidden="true" />{tp('Accept all {n} suggestions', acceptAll.length, { n: acceptAll.length })}
      </button>}
      {error && <div className="el-alert is-error" role="alert"><span>{error}</span><button type="button" className="el-btn is-small" onClick={onRetry}>{t('Retry')}</button></div>}
      {!loaded && !error && <p className="el-small" role="status">{t('Loading…')}</p>}
      {loaded && !items.length && <p className="el-small">{t('No comments yet.')}</p>}
      <ul className="el-fb-list">{items.map(card)}</ul>
    </div>
  </aside>
}

export default memo(CommentsPanel)
