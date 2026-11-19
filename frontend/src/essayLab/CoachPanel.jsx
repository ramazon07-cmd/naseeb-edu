import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Info, MessageCircleQuestion, RefreshCw, Sparkles, X } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { NOTE_KINDS, coachSource, criteriaRows, isCached, kindOf, noteForQuote, overallScore, resultMode, rubricName, safetyContent } from './coachModel.js'
import { relativeTime } from './format.js'

const ERROR_TEXT = {
  slow_down: 'Give it a few seconds, then check again.',
  coach_resting: 'Coach is resting for today. Your essay is saved — try again tomorrow.',
  coach_unavailable: 'Coach can’t be reached right now. Try again in a minute.',
  empty_essay: 'Write a few sentences first, then ask Coach.',
  stale: 'Your latest words were still saving. Check again.',
}

function ScoreRing({ percent, label }) {
  const radius = 30
  const circumference = 2 * Math.PI * radius
  const dash = (Math.max(0, Math.min(100, percent)) / 100) * circumference
  return <svg className="el-ring" width="72" height="72" viewBox="0 0 72 72" role="img" aria-label={label}>
    <circle cx="36" cy="36" r={radius} className="el-ring-track" />
    <circle cx="36" cy="36" r={radius} className="el-ring-value" strokeDasharray={`${dash} ${circumference}`} transform="rotate(-90 36 36)" />
    <text x="36" y="41" textAnchor="middle" className="el-ring-text">{percent}</text>
  </svg>
}

function ScoreBars({ rows, visibleNotes, evidenceIds, onJump }) {
  const [open, setOpen] = useState(null)
  return <dl className="el-scores">
    {rows.map(({ key, label, value, band, evidence }) => {
      // The server names the note an evidence quote belongs to; matching the quote text is the fallback.
      const linked = evidenceIds?.[key] ? visibleNotes.find((item) => item.id === evidenceIds[key]) : null
      const note = linked || (evidence ? noteForQuote(visibleNotes, evidence) : null)
      const shown = open === key && evidence
      return <div key={key} className="el-score-row">
        <div className="el-score">
          <dt>{t(label)}</dt>
          <dd>
            <span className="el-score-bar" role="img" aria-label={t('{label}: {value} of 4, {band}', { label: t(label), value, band: t(band.label) })}>
              {[1, 2, 3, 4].map((step) => <span key={step} className={step <= value ? `is-on is-${band.tone}` : ''} />)}
            </span>
            <span className="el-score-label">{t(band.label)}</span>
            {evidence && <button type="button" className="el-icon-btn el-score-toggle" aria-expanded={shown} aria-label={t('Show the words behind this score: {label}', { label: t(label) })}
              onClick={() => setOpen(shown ? null : key)}>{shown ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}</button>}
          </dd>
        </div>
        {shown && <blockquote className="el-score-evidence">
          “{evidence}”
          {note && <button type="button" className="el-link" onClick={() => onJump(note)}>{t('Jump to it')}</button>}
        </blockquote>}
      </div>
    })}
  </dl>
}

function SafetyCard({ result }) {
  const { message, resources } = safetyContent(result)
  return <div className="el-coach-safety" role="status">
    <p>{message || t('You are not alone. A person you trust can help with this.')}</p>
    {resources.map((item, index) => <p key={index} className="el-coach-resource">{item.label && <strong>{item.label} </strong>}{item.text}</p>)}
    <p className="el-small">{t('Coach has no score for this text. Your essay is saved.')}</p>
  </div>
}

// Coach panel: overall ring, five score bars, tabs and note cards.
// Notes only show while their quote can still be found in the text.
function CoachPanel({
  check, status, anchored, activeId, dismissed, words, onCheck, onSelect, onJump, onDismiss, onClose,
}) {
  const [tab, setTab] = useState('all')
  const [expanded, setExpanded] = useState(true) // bottom sheet on phones
  const [showSummary, setShowSummary] = useState(false)
  const listRef = useRef(null)
  const result = check?.result
  const safety = resultMode(check) === 'safety'
  const overall = safety ? null : overallScore(result)
  const rows = useMemo(() => (safety ? [] : criteriaRows(result)), [result, safety])
  const rubric = safety ? '' : rubricName(result)

  const visibleNotes = useMemo(() => (safety ? [] : result?.notes || []).filter((note) => anchored.has(note.id) && !dismissed.has(note.id)), [result, safety, anchored, dismissed])
  const goneCount = (safety ? [] : result?.notes || []).filter((note) => !anchored.has(note.id) && !dismissed.has(note.id)).length
  const counts = useMemo(() => Object.fromEntries(NOTE_KINDS.map((kind) => [kind.id, visibleNotes.filter((note) => kindOf(note).id === kind.id).length])), [visibleNotes])
  const notes = tab === 'all' ? visibleNotes : visibleNotes.filter((note) => kindOf(note).id === tab)
  const strengths = (tab === 'all' || tab === 'strength') ? (result?.strengths || []).filter(Boolean) : []

  // Bring the selected card into view when a highlight in the text is clicked.
  useEffect(() => {
    if (!activeId) return
    const card = listRef.current?.querySelector(`[data-note="${CSS.escape(activeId)}"]`)
    card?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    setExpanded(true)
  }, [activeId])

  const tabs = [{ id: 'all', label: 'All', count: visibleNotes.length }, ...NOTE_KINDS.map((kind) => ({ id: kind.id, label: kind.tab, count: counts[kind.id] }))]
  const onTabKey = (event, index) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]
    setTab(next.id)
    event.currentTarget.parentElement?.querySelector(`[data-tab="${next.id}"]`)?.focus()
  }

  const nextNote = (note) => {
    const index = visibleNotes.findIndex((item) => item.id === note.id)
    const next = visibleNotes[(index + 1) % visibleNotes.length]
    if (next) onJump(next)
  }

  const errorText = status.error ? t(ERROR_TEXT[status.error.code] || status.error.message || 'Coach couldn’t check this essay.') : ''
  const activeIndex = visibleNotes.findIndex((note) => note.id === activeId)

  return <aside className={`el-side-panel el-coach${expanded ? ' is-expanded' : ' is-collapsed'}`} aria-label={t('Naseeb Coach')}>
    <button type="button" className="el-sheet-handle" aria-label={expanded ? t('Collapse coach') : t('Expand coach')} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      <span aria-hidden="true" />
    </button>
    <div className="el-coach-head">
      {overall
        ? <ScoreRing percent={overall.percent} label={t('Depth score {n} of 100', { n: overall.percent })} />
        : <span className="el-coach-icon" aria-hidden="true"><Sparkles size={20} /></span>}
      <div className="el-coach-title">
        <strong>{overall ? t('Depth score') : t('Naseeb Coach')}</strong>
        <span>{safety ? t('Checked {when}', { when: relativeTime(check.created_at) }) : check
          ? (visibleNotes.length === 1 ? t('Checked {when} · 1 idea', { when: relativeTime(check.created_at) }) : tp('Checked {when} · {n} ideas', visibleNotes.length, { when: relativeTime(check.created_at), n: visibleNotes.length }))
          : t('Questions that help you go deeper')}</span>
        {overall && <span className={`el-badge is-${overall.band.tone}`}>{t(overall.band.label)}</span>}
      </div>
      <div className="el-coach-actions">
        <button type="button" className="el-btn is-small" onClick={onCheck} disabled={status.loading} aria-busy={status.loading}>
          <RefreshCw size={14} aria-hidden="true" className={status.loading ? 'el-spin' : ''} />{check ? t('Check again') : t('Check depth')}
        </button>
        <button type="button" className="el-icon-btn el-hide-sm" aria-label={t('Hide coach')} title={t('Hide coach')} onClick={onClose}><X size={18} /></button>
        <button type="button" className="el-icon-btn el-show-sm" aria-label={expanded ? t('Collapse coach') : t('Expand coach')} onClick={() => setExpanded((value) => !value)}>
          {expanded ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
        </button>
      </div>
    </div>

    <div className="el-coach-body">
      {status.loading && <div className="el-coach-loading" role="status">
        <span className="el-shimmer" /><span className="el-shimmer is-short" /><span className="el-shimmer" />
        <p>{t('Coach is reading your essay. This can take up to half a minute.')}</p>
      </div>}
      {errorText && !status.loading && <div className="el-alert is-error" role="alert">{errorText}</div>}

      {!check && !status.loading && <div className="el-coach-empty">
        <MessageCircleQuestion size={28} aria-hidden="true" />
        <strong>{t('How deep does your essay go?')}</strong>
        <p>{t('Coach reads your draft and asks questions where a reader will want more: reflection, specific details, your voice and how well you answer the question. It never writes for you.')}</p>
        {words < 80 && <p className="el-small">{t('Tip: it works best once you have a paragraph or two.')}</p>}
      </div>}

      {result && safety && !status.loading && <SafetyCard result={result} />}

      {result && !safety && !status.loading && <>
        {coachSource(check) === 'rules' && <p className="el-alert is-info el-coach-source" role="note">
          <Info size={15} aria-hidden="true" />
          <span><strong>{t('Quick check (built-in rules)')}</strong> {t('AI feedback isn’t available right now, so these ideas come from simple writing checks. They can still help.')}</span>
        </p>}
        {rows.length > 0 && <ScoreBars rows={rows} visibleNotes={visibleNotes} evidenceIds={result?.evidence_ids} onJump={onJump} />}
        {(rubric || isCached(check)) && <p className="el-small el-coach-rubric">
          {rubric && (result.rubric_version != null
            ? t('Scored with the {name} rubric v{version}', { name: t(rubric), version: result.rubric_version })
            : t('Scored with the {name} rubric', { name: t(rubric) }))}
          {rubric && isCached(check) && ' · '}
          {isCached(check) && t('Same essay, same result. Change your text to check again.')}
        </p>}
        {result.summary && <div className="el-coach-summary">
          <p className={showSummary ? '' : 'is-clamped'}>{result.summary}</p>
          {result.summary.length > 140 && <button type="button" className="el-link" onClick={() => setShowSummary((value) => !value)}>{showSummary ? t('Show less') : t('Read more')}</button>}
        </div>}

        <div role="tablist" aria-label={t('Coach notes')} className="el-tabs">
          {tabs.map((item, index) => <button key={item.id} type="button" role="tab" data-tab={item.id} id={`el-tab-${item.id}`}
            aria-selected={tab === item.id} aria-controls="el-coach-list" tabIndex={tab === item.id ? 0 : -1}
            className={`el-tab is-${item.id}${tab === item.id ? ' is-on' : ''}`} onClick={() => setTab(item.id)} onKeyDown={(event) => onTabKey(event, index)}>
            {t(item.label)} <span className="el-tab-count">{item.count}</span>
          </button>)}
        </div>

        <div id="el-coach-list" role="tabpanel" aria-labelledby={`el-tab-${tab}`} className="el-notes" ref={listRef}>
          {notes.map((note) => {
            const kind = kindOf(note)
            const open = note.id === activeId
            return <article key={note.id} data-note={note.id} className={`el-note is-${kind.id}${open ? ' is-open' : ''}`}>
              <button type="button" className="el-note-head" aria-expanded={open} onClick={() => onSelect(open ? null : note)}>
                <span className="el-dot" aria-hidden="true" />
                <span className="el-note-kind">{t(kind.label)}</span>
                <span className="el-note-title">{note.question}</span>
              </button>
              {open && <div className="el-note-body">
                <blockquote>“{note.quote}”</blockquote>
                <div className="el-ask"><strong>{kind.id === 'strength' ? t('Why it works') : t('Ask yourself')}</strong><span>{note.question}</span></div>
                {note.why && <p className="el-why"><Info size={14} aria-hidden="true" />{note.why}</p>}
                <div className="el-note-actions">
                  <button type="button" className="el-btn is-small is-primary" onClick={() => onJump(note)}>{kind.id === 'strength' ? t('Show me') : t('Jump to it')}</button>
                  <button type="button" className="el-btn is-small" onClick={() => onDismiss(note)}>{kind.id === 'strength' ? t('Got it') : t('Dismiss')}</button>
                  {visibleNotes.length > 1 && <button type="button" className="el-btn is-small is-ghost el-next" onClick={() => nextNote(note)}>
                    {t('Next idea')} <span className="el-small">{activeIndex + 1}/{visibleNotes.length}</span>
                  </button>}
                </div>
              </div>}
            </article>
          })}
          {strengths.map((text, index) => <div key={`s${index}`} className="el-strength-card"><span className="el-dot" aria-hidden="true" /><span>{text}</span></div>)}
          {!notes.length && !strengths.length && <p className="el-empty">{visibleNotes.length || tab !== 'all' ? t('Nothing in this group.') : t('No open ideas. Nice work — check again after your next revision.')}</p>}
          {goneCount > 0 && <p className="el-small el-gone">{goneCount === 1 ? t('1 idea disappeared because you changed that sentence.') : tp('{n} ideas disappeared because you changed those sentences.', goneCount, { n: goneCount })}</p>}
        </div>
      </>}
    </div>

    <div className="el-coach-foot"><Info size={15} aria-hidden="true" /><span>{t('Coach asks questions. It never writes your essay for you.')}</span></div>
  </aside>
}

export default memo(CoachPanel)
