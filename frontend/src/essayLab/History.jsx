import { Fragment, memo, useCallback, useEffect, useState } from 'react'
import { Bookmark, Eye, History as HistoryIcon, RotateCcw, X } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { essayLabApi } from './essayLabApi.js'
import { checkpointDate, dayGroup, relativeTime } from './format.js'
import { fontStack, loadFontsInJson } from './fonts.js'

const REASONS = {
  auto: { title: 'Autosaved version', note: 'kept automatically' },
  depth_check: { title: 'Before depth check', note: 'kept automatically' },
  restore: { title: 'Before restoring an older version', note: 'kept automatically' },
  manual: { title: 'Saved by you', note: 'named by you' },
}

function checkpointTitle(checkpoint) {
  if (checkpoint.label) return checkpoint.reason === 'manual' ? t('“{label}”', { label: checkpoint.label }) : checkpoint.label
  return t(REASONS[checkpoint.reason]?.title || 'Saved version')
}

// Checkpoint history: newest first, grouped by day, with preview and restore.
function History({ essayId, tabId, version, words, savedAt, previewId, onPreview, onRestore, onBeforeName, onClose }) {
  const [state, setState] = useState({ loading: true, error: '', items: [] })
  const [naming, setNaming] = useState(false)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: '' }))
    try {
      const items = await essayLabApi.checkpoints(essayId, tabId)
      setState({ loading: false, error: '', items: Array.isArray(items) ? items : [] })
    } catch (error) {
      setState({ loading: false, error: error?.message || t('Could not load the history.'), items: [] })
    }
  }, [essayId, tabId])

  useEffect(() => { load() }, [load, version])

  async function nameVersion(event) {
    event.preventDefault()
    setBusy('name')
    try {
      await onBeforeName()
      await essayLabApi.createCheckpoint(essayId, tabId, label.trim().slice(0, 120))
      setNaming(false)
      setLabel('')
      await load()
    } catch (error) {
      setState((current) => ({ ...current, error: error?.message || t('Could not save this version.') }))
    } finally {
      setBusy(null)
    }
  }

  async function run(kind, checkpoint, action) {
    setBusy(`${kind}${checkpoint.id}`)
    try { await action(checkpoint) } finally { setBusy(null) }
  }

  let lastGroup = null
  return <aside className="el-side-panel el-history" aria-label={t('Version history')}>
    <div className="el-history-head">
      <HistoryIcon size={18} aria-hidden="true" />
      <strong>{t('Version history')}</strong>
      <button type="button" className="el-icon-btn" aria-label={t('Close version history')} title={t('Close')} onClick={onClose}><X size={18} /></button>
    </div>
    <div className="el-history-body">
      <span className="el-group-label">{t('NOW')}</span>
      <div className={`el-version is-current${previewId == null ? ' is-selected' : ''}`}>
        <strong>{t('Current version')}</strong>
        <span>{tp('{when} · {n} words', words, { when: relativeTime(savedAt) || t('not saved yet'), n: words })}</span>
        {previewId != null && <button type="button" className="el-link" onClick={() => onPreview(null)}>{t('Back to current')}</button>}
      </div>

      {state.loading && !state.items.length && <p className="el-small" role="status">{t('Loading…')}</p>}
      {state.error && <div className="el-alert is-error" role="alert"><span>{state.error}</span><button type="button" className="el-btn is-small" onClick={load}>{t('Retry')}</button></div>}
      {!state.loading && !state.items.length && !state.error && <p className="el-small">{t('Versions are kept automatically as you write (every 10 minutes of changes), before each depth check and before a restore.')}</p>}

      {state.items.map((checkpoint) => {
        const group = dayGroup(checkpoint.created_at)
        const header = group !== lastGroup ? <span className="el-group-label">{t(group.toUpperCase())}</span> : null
        lastGroup = group
        const selected = previewId === checkpoint.id
        return <Fragment key={checkpoint.id}>
          {header}
          <div className={`el-version${selected ? ' is-selected' : ''}`}>
            <strong>{checkpointTitle(checkpoint)}</strong>
            <span>{checkpointDate(checkpoint.created_at)} · {tp('{n} words', checkpoint.word_count ?? 0, { n: checkpoint.word_count ?? 0 })} · {t(REASONS[checkpoint.reason]?.note || 'saved')}</span>
            <div className="el-version-actions">
              <button type="button" className="el-btn is-small" aria-pressed={selected} disabled={busy === `p${checkpoint.id}`}
                onClick={() => (selected ? onPreview(null) : run('p', checkpoint, onPreview))}>
                <Eye size={14} aria-hidden="true" />{selected ? t('Previewing') : t('Preview')}
              </button>
              <button type="button" className="el-btn is-small" disabled={busy === `r${checkpoint.id}`} aria-busy={busy === `r${checkpoint.id}`}
                onClick={() => run('r', checkpoint, onRestore)}>
                <RotateCcw size={14} aria-hidden="true" />{t('Restore')}
              </button>
            </div>
          </div>
        </Fragment>
      })}

      {naming
        ? <form className="el-name-version" onSubmit={nameVersion}>
          <label className="el-label" htmlFor="el-version-name">{t('Name this version')}</label>
          <input id="el-version-name" autoFocus className="el-input is-small" maxLength={120} placeholder={t('e.g. “radio idea” or “sent to counselor”')}
            value={label} onChange={(event) => setLabel(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape') setNaming(false) }} />
          <div className="el-note-actions">
            <button type="submit" className="el-btn is-small is-primary" disabled={busy === 'name'} aria-busy={busy === 'name'}>{t('Save version')}</button>
            <button type="button" className="el-btn is-small" onClick={() => setNaming(false)}>{t('Cancel')}</button>
          </div>
        </form>
        : <button type="button" className="el-dashed-btn" onClick={() => setNaming(true)}><Bookmark size={15} aria-hidden="true" />{t('Name this version…')}</button>}
    </div>
  </aside>
}

export default memo(History)

// Read-only rendering of a checkpoint's document (no editor needed).
function markStyle(mark) {
  if (mark.type === 'textStyle') {
    const { fontFamily, fontSize, color } = mark.attrs || {}
    return { fontFamily: fontStack(fontFamily) || undefined, fontSize: fontSize ? `calc(var(--el-pt, 1pt) * ${fontSize})` : undefined, color: color || undefined }
  }
  return null
}

function renderInline(nodes = []) {
  return nodes.map((node, index) => {
    if (node.type === 'hardBreak') return <br key={index} />
    if (node.type !== 'text') return null
    let content = node.text
    for (const mark of node.marks || []) {
      if (mark.type === 'bold') content = <strong>{content}</strong>
      else if (mark.type === 'italic') content = <em>{content}</em>
      else if (mark.type === 'underline') content = <u>{content}</u>
      else if (mark.type === 'strike') content = <s>{content}</s>
      else if (mark.type === 'textStyle') content = <span style={markStyle(mark)}>{content}</span>
      else if (mark.type === 'highlight') content = <mark className="el-highlight" style={{ backgroundColor: mark.attrs?.color }}>{content}</mark>
      else if (mark.type === 'link') content = <u className="el-preview-link">{content}</u>
    }
    return <Fragment key={index}>{content}</Fragment>
  })
}

function blockStyle(node) {
  const { textAlign, lineHeight, indent } = node.attrs || {}
  if (!textAlign && !lineHeight && !indent) return undefined
  return { textAlign, lineHeight, marginLeft: indent ? `calc(var(--el-pt, 1pt) * ${36 * indent})` : undefined }
}

function renderBlock(node, index) {
  const children = () => (node.content || []).map(renderBlock)
  const style = blockStyle(node)
  switch (node?.type) {
    case 'paragraph': return <p key={index} style={style}>{renderInline(node.content)}</p>
    case 'title': return <p key={index} className="el-title" style={style}>{renderInline(node.content)}</p>
    case 'subtitle': return <p key={index} className="el-subtitle" style={style}>{renderInline(node.content)}</p>
    case 'heading': {
      const Tag = `h${[1, 2, 3].includes(node.attrs?.level) ? node.attrs.level : 1}`
      return <Tag key={index} style={style}>{renderInline(node.content)}</Tag>
    }
    case 'pageBreak': return <div key={index} className="el-page-break" aria-hidden="true" />
    case 'blockquote': return <blockquote key={index}>{children()}</blockquote>
    case 'bulletList': return <ul key={index} className={node.attrs?.style === 'dash' ? 'list-dash' : undefined}>{children()}</ul>
    case 'orderedList': return <ol key={index} start={node.attrs?.start ?? 1}>{children()}</ol>
    case 'listItem': return <li key={index}>{children()}</li>
    default: return null
  }
}

export function DocPreview({ doc }) {
  loadFontsInJson(doc)
  return <div className="el-prose is-preview" aria-readonly="true">{(doc?.content || []).map(renderBlock)}</div>
}
