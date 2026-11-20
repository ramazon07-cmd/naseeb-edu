import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronUp, Compass, Feather, Info, LayoutList, Lightbulb, MessageCircleQuestion, RefreshCw, Lock, Sparkles, Star, Target, Undo2, X } from 'lucide-react'
import { t, tp } from '../i18n.js'
import {
  CRITERIA, STRENGTHS, coachSource, deltaSince, doneNotes, goneNotes, headline, levelWord, normalizeCheck, openNotes, recheckBlock,
} from './coachModel.js'

const ERROR_TEXT = {
  slow_down: 'Give it a few seconds, then check again.',
  coach_resting: 'Coach is resting for today. Your essay is saved — try again tomorrow.',
  coach_unavailable: 'Coach can’t be reached right now. Try again in a minute.',
  empty_essay: 'Write a few sentences first, then ask Coach.',
  stale: 'Your latest words were still saving. Check again.',
  notes_open: 'Resolve all notes first',
  too_small_change: 'Change a few more words before checking again',
}

const BLOCK_TEXT = {
  notes_open: 'Resolve all notes first',
  unchanged: 'Change your essay first',
}

const CRITERION_ICON = { reflection: Lightbulb, specificity: Target, voice: Feather, structure: LayoutList, prompt_fit: Compass, [STRENGTHS]: Star }

const EXPLAIN = {
  reflection: 'Do you say what you learned or felt, not only what happened?',
  specificity: 'Real moments, names and details a reader can picture.',
  voice: 'Does it sound like you and nobody else?',
  structure: 'Does each part lead clearly to the next?',
  prompt_fit: 'Does the essay answer the question it was asked?',
}

const DAILY_CHECKS = 5

function CriterionIcon({ criterion, size = 16 }) {
  const Icon = CRITERION_ICON[criterion] || Lightbulb
  return <Icon size={size} aria-hidden="true" className="el-co-kic" />
}

function ScoreRing({ percent, label }) {
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const dash = (Math.max(0, Math.min(100, percent)) / 100) * circumference
  return <div className="el-ring-wrap" role="img" aria-label={label}>
    <svg className="el-ring" width="88" height="88" viewBox="0 0 88 88" aria-hidden="true">
      <circle cx="44" cy="44" r={radius} className="el-ring-track" />
      <circle cx="44" cy="44" r={radius} className="el-ring-value" strokeDasharray={`${dash} ${circumference}`} transform="rotate(-90 44 44)" />
    </svg>
    <span className="el-ring-num"><b>{percent}</b><small>/100</small></span>
  </div>
}

function Meter({ value, criterion, label }) {
  const level = Math.max(0, Math.min(4, Math.round(Number(value)) || 0))
  return <span className={`el-co-meter is-${criterion}`} role="img" aria-label={label}>
    {[1, 2, 3, 4].map((step) => <span key={step} className={step <= level ? 'is-on' : ''} />)}
  </span>
}

function noteCount(n) {
  return n === 1 ? t('1 note') : tp('{n} notes', n, { n })
}

// Coach panel: sticky header (score), tabs, scrollable content and a sticky footer
// with the one "Check again" button. Notes only count while their quote can be found.
function CoachPanel({
  check, status, anchored, activeId, states, changed, notice, words,
  onCheck, onJump, onSetState, onClose,
}) {
  const [tab, setTab] = useState('overview')
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(true) // bottom sheet on phones
  const [showSummary, setShowSummary] = useState(false)
  const [openCriterion, setOpenCriterion] = useState(null)
  const [showDone, setShowDone] = useState(false)
  const bodyRef = useRef(null)

  const model = useMemo(() => normalizeCheck(check), [check])
  const notes = model?.notes
  const open = useMemo(() => openNotes(notes, states, anchored), [notes, states, anchored])
  const done = useMemo(() => doneNotes(notes, states), [notes, states])
  const gone = useMemo(() => goneNotes(notes, states, anchored), [notes, states, anchored])
  const total = open.length + done.length
  const chips = useMemo(() => CRITERIA.map((item) => ({ ...item, count: open.filter((note) => note.criterion === item.key).length })).filter((item) => item.count > 0), [open])
  const activeFilter = filter === 'all' || chips.some((chip) => chip.key === filter) ? filter : 'all'
  const shown = activeFilter === 'all' ? open : open.filter((note) => note.criterion === activeFilter)
  const strengths = model?.strengths || []
  const locked = Boolean(model?.notesLocked)

  // A new check starts again from the overview.
  const checkId = check?.id
  useEffect(() => {
    setTab('overview'); setFilter('all'); setOpenCriterion(null); setShowDone(false); setShowSummary(false)
  }, [checkId])

  // A highlight clicked in the text selects its card here.
  useEffect(() => {
    if (!activeId || !model) return
    const isStrength = strengths.some((item) => item.id === activeId) && !notes.some((note) => note.id === activeId)
    setTab(isStrength ? 'strengths' : 'notes')
    if (!isStrength) {
      const note = notes.find((item) => item.id === activeId)
      if (note) setFilter((current) => (current === 'all' || current === note.criterion ? current : 'all'))
    }
    setExpanded(true)
    const id = window.requestAnimationFrame(() => {
      bodyRef.current?.querySelector(`[data-note="${CSS.escape(activeId)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
    return () => window.cancelAnimationFrame(id)
    // Only the selection matters here, not every re-render of the lists.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'notes', label: 'Notes', count: locked ? 0 : open.length },
    { id: 'strengths', label: 'Strengths', count: strengths.length, good: true },
  ]
  const onTabKey = (event, index) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]
    setTab(next.id)
    event.currentTarget.parentElement?.querySelector(`[data-tab="${next.id}"]`)?.focus()
  }

  const showNotes = (criterion) => { setFilter(criterion); setTab('notes') }

  const scored = Boolean(model?.scored)
  const delta = scored ? deltaSince(model.overall, check?.previous_overall) : null
  const block = status.loading ? null : recheckBlock({ hasCheck: Boolean(check), openCount: open.length, changed })
  const blockText = block ? t(BLOCK_TEXT[block]) : ''
  const errorCode = status.error?.code
  const errorText = status.error ? t(ERROR_TEXT[errorCode] || status.error.message || 'Coach couldn’t check this essay.') : ''
  const footerError = errorCode === 'notes_open' || errorCode === 'too_small_change'
  const checksLeft = Number.isFinite(Number(check?.checks_left)) && check?.checks_left !== null ? Math.max(0, Number(check.checks_left)) : null
  const hint = status.loading ? '' : footerError ? errorText : notice === 'reused' ? t('Already checked — nothing changed') : blockText
  const hintId = 'el-coach-hint'

  return <aside className={`el-side-panel el-coach${expanded ? ' is-expanded' : ' is-collapsed'}`} aria-label={t('Naseeb Coach')}>
    <button type="button" className="el-sheet-handle" aria-label={expanded ? t('Collapse coach') : t('Expand coach')} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      <span aria-hidden="true" />
    </button>
    <div className="el-coach-head">
      {scored
        ? <ScoreRing percent={model.overall} label={t('Depth score {n} of 100', { n: model.overall })} />
        : <span className="el-coach-icon" aria-hidden="true"><Sparkles size={22} /></span>}
      <div className="el-coach-title">
        <strong>{scored ? t(headline(model.overall)) : check ? t('Quick check') : t('Naseeb Coach')}</strong>
        {delta !== null && <span className="el-co-delta">{t('+{n} since last check', { n: delta })}</span>}
      </div>
      <div className="el-coach-actions">
        <button type="button" className="el-icon-btn el-hide-sm" aria-label={t('Hide coach')} title={t('Hide coach')} onClick={onClose}><X size={18} /></button>
        <button type="button" className="el-icon-btn el-show-sm" aria-label={expanded ? t('Collapse coach') : t('Expand coach')} onClick={() => setExpanded((value) => !value)}>
          {expanded ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
        </button>
      </div>
    </div>

    {model && !status.loading && <div role="tablist" aria-label={t('Coach')} className="el-tabs">
      {tabs.map((item, index) => <button key={item.id} type="button" role="tab" data-tab={item.id} id={`el-tab-${item.id}`}
        aria-selected={tab === item.id} aria-controls="el-coach-panel" tabIndex={tab === item.id ? 0 : -1}
        className={`el-tab${tab === item.id ? ' is-on' : ''}`} onClick={() => setTab(item.id)} onKeyDown={(event) => onTabKey(event, index)}>
        {t(item.label)}{item.count > 0 && <span className={`el-tab-count${item.good ? ' is-good' : ''}`}>{item.count}</span>}
      </button>)}
    </div>}

    <div className="el-coach-body" ref={bodyRef} id="el-coach-panel" role={model ? 'tabpanel' : undefined} aria-labelledby={model ? `el-tab-${tab}` : undefined}>
      {status.loading && <div className="el-coach-loading" role="status">
        <span className="el-shimmer is-big" /><span className="el-shimmer" /><span className="el-shimmer is-short" />
        <p>{t('Coach is reading your essay. This can take up to half a minute.')}</p>
      </div>}
      {errorText && !footerError && !status.loading && <div className="el-alert is-error" role="alert">{errorText}</div>}

      {!check && !status.loading && <div className="el-coach-empty">
        <MessageCircleQuestion size={28} aria-hidden="true" />
        <strong>{t('How deep does your essay go?')}</strong>
        <p>{t('Coach reads your draft and asks questions where a reader will want more: reflection, specific details, your voice and how well you answer the question.')}</p>
        <p className="el-co-never">{t('Coach asks questions. It never writes your essay for you.')}</p>
        {words < 80 && <p className="el-small">{t('Tip: it works best once you have a paragraph or two.')}</p>}
      </div>}

      {model && !status.loading && <>
        {coachSource(check) === 'rules' && <p className="el-alert is-info el-coach-source" role="note">
          <Info size={15} aria-hidden="true" />
          <span>{t('AI feedback isn’t available right now, so these ideas come from simple writing checks. They can still help.')}</span>
        </p>}

        {tab === 'overview' && <>
          {scored && model.overall <= 50 && <section className="el-co-card el-co-bigpicture">
            <h3>{t('Big picture first')}</h3>
            {model.summary && <p>{model.summary}</p>}
            {model.suggestions.length > 0 && <ol className="el-co-steps">
              {model.suggestions.map((text, index) => <li key={index}><span className="el-co-step-n" aria-hidden="true">{index + 1}</span><span>{text}</span></li>)}
            </ol>}
          </section>}

          {Object.keys(model.scores).length > 0 && <section className="el-co-card">
            <h3>{t('Five criteria')}</h3>
            <ul className="el-co-crit">
              {CRITERIA.map(({ key, label }) => {
                const value = Number(model.scores[key]) || 0
                const word = levelWord(value)
                const count = open.filter((note) => note.criterion === key).length
                const isOpen = openCriterion === key
                return <li key={key} className={`is-${key}`}>
                  <div className="el-co-crit-row">
                    <button type="button" className="el-co-crit-main" aria-expanded={isOpen} onClick={() => setOpenCriterion(isOpen ? null : key)}>
                      <span className="el-co-crit-name">{t(label)}</span>
                      <Meter value={value} criterion={key} label={word ? t('{label}: {value} of 4, {band}', { label: t(label), value, band: t(word) }) : t(label)} />
                      <span className="el-co-crit-level">{word ? t(word) : ''}</span>
                      <ChevronDown size={16} aria-hidden="true" className="el-co-crit-chev" />
                    </button>
                    {count > 0 && !locked && <button type="button" className="el-co-crit-count" onClick={() => showNotes(key)}>{noteCount(count)}</button>}
                  </div>
                  {isOpen && <p className="el-co-crit-explain">{t(EXPLAIN[key])}</p>}
                </li>
              })}
            </ul>
          </section>}

          {!(scored && model.overall <= 50) && model.summary && <section className="el-co-card">
            <h3>{t('Summary')}</h3>
            <p className={`el-co-summary${showSummary ? '' : ' is-clamped'}`}>{model.summary}</p>
            {model.summary.length > 140 && <button type="button" className="el-link" onClick={() => setShowSummary((value) => !value)}>{showSummary ? t('Show less') : t('Read more')}</button>}
          </section>}
        </>}

        {tab === 'notes' && (locked
          ? <div className="el-co-card el-co-locked">
            <span className="el-coach-icon" aria-hidden="true"><Lock size={22} /></span>
            <strong>{t('Notes unlock at 51')}</strong>
            <p>{t('Work on the big picture first.')}</p>
          </div>
          : <>
            {chips.length > 0 && <div className="el-co-chips" role="group" aria-label={t('Filter notes')}>
              <button type="button" className={`el-co-chip${activeFilter === 'all' ? ' is-on' : ''}`} aria-pressed={activeFilter === 'all'} onClick={() => setFilter('all')}>
                {t('All')} <b>{open.length}</b>
              </button>
              {chips.map((chip) => <button key={chip.key} type="button" className={`el-co-chip is-${chip.key}${activeFilter === chip.key ? ' is-on' : ''}`} aria-pressed={activeFilter === chip.key} onClick={() => setFilter(chip.key)}>
                <i className="el-co-chip-dot" aria-hidden="true" />{t(chip.label)} <b>{chip.count}</b>
              </button>)}
            </div>}
            {total > 0 && <div className="el-co-progress-note">
              <span className="el-co-bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done.length} aria-label={t('{done} of {total} done', { done: done.length, total })}>
                <span style={{ width: `${(done.length / total) * 100}%` }} />
              </span>
              <span className="el-small">{t('{done} of {total} done', { done: done.length, total })}</span>
            </div>}

            <div className="el-notes">
              {shown.map((note) => {
                const active = note.id === activeId
                return <article key={note.id} data-note={note.id} className={`el-note is-${note.criterion}${active ? ' is-active' : ''}`} onClick={() => onJump(note)}>
                  <div className="el-note-top">
                    <CriterionIcon criterion={note.criterion} />
                    {note.priority && <span className="el-co-flag">{t('Priority')}</span>}
                    <span className="el-co-sp" />
                    <button type="button" className="el-co-corner is-ok" aria-label={t('Mark as done')} title={t('Mark as done')}
                      onClick={(event) => { event.stopPropagation(); onSetState(note, 'done') }}><Check size={15} aria-hidden="true" /></button>
                    <button type="button" className="el-co-corner" aria-label={t('Not useful')} title={t('Not useful')}
                      onClick={(event) => { event.stopPropagation(); onSetState(note, 'dismissed') }}><X size={15} aria-hidden="true" /></button>
                  </div>
                  <button type="button" className="el-note-main" aria-pressed={active}>
                    <span className="el-note-q">{note.question}</span>
                    {note.context && <span className="el-note-ctx">{note.context}</span>}
                  </button>
                </article>
              })}
              {!shown.length && <p className="el-empty">{open.length ? t('Nothing in this group.') : t('All notes done.')}</p>}
            </div>

            {done.length > 0 && <div className="el-co-done">
              <button type="button" className="el-co-done-toggle" aria-expanded={showDone} onClick={() => setShowDone((value) => !value)}>
                <Check size={15} aria-hidden="true" />{t('Done ({n})', { n: done.length })}
                <ChevronDown size={15} aria-hidden="true" className="el-co-crit-chev" />
              </button>
              {showDone && <ul>
                {done.map((note) => <li key={note.id}>
                  <span title={note.question}>{note.question}</span>
                  <button type="button" className="el-link" onClick={() => onSetState(note, 'open')}><Undo2 size={13} aria-hidden="true" />{t('Undo')}</button>
                </li>)}
              </ul>}
            </div>}
            {gone.length > 0 && <p className="el-small el-gone">{gone.length === 1 ? t('1 idea no longer matches your text') : tp('{n} ideas no longer match your text', gone.length, { n: gone.length })}</p>}
          </>)}

        {tab === 'strengths' && <div className="el-notes">
          {strengths.map((item) => {
            const jumpable = Boolean(item.quote) && anchored.has(item.id)
            const body = <>
              <Star size={15} aria-hidden="true" className="el-co-kic" />
              <span>{item.text}</span>
            </>
            return jumpable
              ? <button key={item.id} type="button" data-note={item.id} className={`el-strength-card is-link${item.id === activeId ? ' is-active' : ''}`} onClick={() => onJump({ id: item.id })}>{body}</button>
              : <div key={item.id} data-note={item.id} className="el-strength-card">{body}</div>
          })}
          {!strengths.length && <p className="el-empty">{t('Nothing in this group.')}</p>}
        </div>}
      </>}
    </div>

    <div className="el-coach-foot">
      <div className="el-co-foot-row">
        <div className="el-co-foot-info">
          {checksLeft !== null && <span className="el-co-left" title={t('Re-checking unchanged text is free')}>
            <span className="el-co-pips" aria-hidden="true">
              {Array.from({ length: DAILY_CHECKS }, (_, index) => <i key={index} className={index < Math.min(DAILY_CHECKS, checksLeft) ? '' : 'is-used'} />)}
            </span>
            {t('{n} left today', { n: checksLeft })}
          </span>}
          {check && <span className={`el-co-state${changed ? ' is-changed' : ''}`}><i aria-hidden="true" />{changed ? t('Text changed') : t('Up to date')}</span>}
        </div>
        <span className="el-co-check-wrap" title={blockText || undefined}>
          <button type="button" className="el-btn is-primary" onClick={onCheck} disabled={status.loading || Boolean(block)} aria-busy={status.loading} aria-describedby={hint ? hintId : undefined}>
            <RefreshCw size={14} aria-hidden="true" className={status.loading ? 'el-spin' : ''} />{check ? t('Check again') : t('Check depth')}
          </button>
        </span>
      </div>
      {hint && <p id={hintId} className={`el-co-foot-hint${footerError ? ' is-error' : ''}`} role={footerError ? 'alert' : 'status'}>{hint}</p>}
    </div>
  </aside>
}

export default memo(CoachPanel)
