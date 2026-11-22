import { memo, useMemo, useState } from 'react'
import { Check, ChevronDown, Copy, HelpCircle, Info, Lock, MessageCircleQuestion, Plus, RefreshCw, ShieldAlert, Sparkles, Undo2, X } from 'lucide-react'
import { formatDateLocale, t, tp } from '../i18n.js'
import { SCORE_HIDDEN_TEXT, coachSource, deltaSince, doneNotes, goneNotes, headline, levelWord, openNotes, recheckBlock } from '../essayLab/coachModel.js'
import { LETTER_CRITERIA, aiIdeasOf, canInsert, checkAvailability, fillCheckText, fillExtras, fillStudent, letterCriterionLabel } from './letterModel.js'

const SOURCE_LABELS = { academics: 'Academics', honor: 'Honor', activity: 'Activity', achievement: 'Achievement', research: 'Research', internship: 'Internship', project: 'Project' }
const DAILY_CHECKS = 5

const ERROR_TEXT = {
  slow_down: 'Give it a few seconds, then check again.',
  coach_resting: 'Check is resting for today. Your letter is saved. Try again tomorrow.',
  coach_unavailable: 'Check depth isn’t available right now.',
  counselors_only: 'Only counselors can use Check.',
  empty_letter: 'Write a few sentences first, then check.',
  stale: 'Your latest words were still saving. Check again.',
  conflict: 'This letter changed elsewhere. Choose a version above.',
  notes_open: 'Resolve all notes first',
  too_small_change: 'Change a few more words before checking again',
}

function ScoreRing({ percent, label }) {
  const radius = 30
  const circumference = 2 * Math.PI * radius
  const dash = (Math.max(0, Math.min(100, percent)) / 100) * circumference
  return <div className="lw-ring" role="img" aria-label={label}>
    <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true">
      <circle cx="36" cy="36" r={radius} className="lw-ring-track" />
      <circle cx="36" cy="36" r={radius} className="lw-ring-value" strokeDasharray={`${dash} ${circumference}`} transform="rotate(-90 36 36)" />
    </svg>
    <b>{percent}</b>
  </div>
}

const sourceName = (source) => t(SOURCE_LABELS[source] || 'Profile')

// Profile facts can be inserted as a neutral "Title: detail." line. AI ideas are questions to the author:
// they cite one fact and are never inserted (Naseeb AI never writes the letter).
function IdeasTab({ ideas, name, onInsertFact }) {
  const { facts, factsLoading, factsError, ai } = ideas
  const items = aiIdeasOf(ai.items)
  return <div className="lw-ideas">
    <div className="lw-sec"><h3>{t('Not in the letter yet')}</h3><span>{t('From the profile')}</span></div>
    {facts.length > 0 && <p className="lw-note lw-fine">{t('From the student’s profile (self-reported). Check before you use them.')}</p>}
    {factsError && <p className="lw-note is-error" role="alert">{factsError}</p>}
    {factsLoading && !facts.length && <p className="lw-note" role="status">{t('Reading the profile…')}</p>}
    <ul className="lw-cards">
      {facts.map((fact, index) => <li key={`${fact.source}-${fact.title}-${index}`} className="lw-card lw-fact">
        <span className="lw-kicker">{sourceName(fact.source)}</span>
        {fact.title && <b>{fact.title}</b>}
        {fact.detail && <small>{fact.detail}</small>}
        {canInsert(fact) && <button type="button" className="lw-plus" onClick={() => onInsertFact(fact)} aria-label={t('Add to the letter: {text}', { text: fact.title || sourceName(fact.source) })} title={t('Add to the letter')}><Plus size={16} aria-hidden="true" /></button>}
      </li>)}
    </ul>
    {!factsLoading && !factsError && !facts.length && <p className="lw-note">{t('Nothing new to suggest from the profile.')}</p>}

    {(items.length > 0 || (ai.available !== false && ai.asked)) && <>
      <div className="lw-sec"><h3>{t('AI ideas')}</h3><span>{t('Questions for you')}</span></div>
      {ai.error && <p className="lw-note is-error" role="alert">{ai.error}</p>}
      {ai.loading && <p className="lw-note" role="status">{t('Thinking…')}</p>}
      {ai.unavailable && !ai.loading && !ai.error && <p className="lw-note">{t('AI ideas aren’t available right now.')}</p>}
      <ul className="lw-cards">
        {items.map((item, index) => <li key={`${item.kind}-${index}-${item.text}`} className="lw-card lw-idea is-question">
          {item.source && <span className="lw-chip">{item.title || sourceName(item.source)}</span>}
          <p><HelpCircle size={15} aria-hidden="true" className="lw-q-icon" />{fillStudent(item.text, name)}</p>
        </li>)}
      </ul>
    </>}
    <p className="lw-note lw-fine">{t('Ideas can be wrong. Check every fact before you send the letter.')}</p>
  </div>
}

// A reader note or a sensitive-content note: no score, no done/not useful buttons, just a question and its sentence.
function ExtraCard({ note, label, active, onJump }) {
  return <article data-note={note.id} className={`lw-note-card is-${note.criterion}${active ? ' is-active' : ''}`}>
    <div className="lw-note-top"><span className="lw-note-crit">{label}</span></div>
    <button type="button" className="lw-note-main" aria-pressed={active} onClick={() => onJump(note)}>
      <span className="lw-note-q">{note.kind ? t(note.question) : note.question}</span>
    </button>
  </article>
}

function CheckTab({ check, model: rawModel, extras: rawExtras, name, status, anchored, activeId, states, onJump, onSetState, words }) {
  const model = useMemo(() => fillCheckText(rawModel, name), [rawModel, name])
  const extras = useMemo(() => fillExtras(rawExtras, name), [rawExtras, name])
  const [filter, setFilter] = useState('all')
  const [openCriterion, setOpenCriterion] = useState(null)
  const [showDone, setShowDone] = useState(false)
  const notes = model?.notes
  const open = useMemo(() => openNotes(notes, states, anchored), [notes, states, anchored])
  const done = useMemo(() => doneNotes(notes, states), [notes, states])
  const gone = useMemo(() => goneNotes(notes, states, anchored), [notes, states, anchored])
  const locked = Boolean(model?.notesLocked)
  const scored = Boolean(model?.scored)
  const delta = scored ? deltaSince(model.overall, check?.previous_overall) : null
  const chips = LETTER_CRITERIA.map((item) => ({ ...item, count: open.filter((note) => note.criterion === item.key).length })).filter((item) => item.count > 0)
  const activeFilter = filter === 'all' || chips.some((chip) => chip.key === filter) ? filter : 'all'
  const shown = activeFilter === 'all' ? open : open.filter((note) => note.criterion === activeFilter)

  return <>
    <p className="lw-lock"><Lock size={14} aria-hidden="true" />{t('Only you see this. The student never does.')}</p>
    {status.loading && <div className="lw-loading" role="status"><span className="lw-shimmer is-big" /><span className="lw-shimmer" /><span className="lw-shimmer is-short" /><p>{t('Reading your letter. This can take up to a minute or two.')}</p></div>}
    {!check && !status.loading && <div className="lw-empty">
      <MessageCircleQuestion size={28} aria-hidden="true" />
      <strong>{t('How deep does your letter go?')}</strong>
      <p>{t('Check reads the letter and asks questions where a committee will want more: evidence, insight, comparison, structure and your voice.')}</p>
      <p className="lw-fine">{t('Check asks questions. It never writes the letter for you.')}</p>
      {words < 80 && <p className="lw-fine">{t('Tip: it works best once you have a paragraph or two.')}</p>}
    </div>}
    {model && !status.loading && extras.safety && <p className="lw-note is-warn" role="alert"><ShieldAlert size={16} aria-hidden="true" />{t('This letter may describe a child in current danger, so it was not scored. Please follow your school’s child-protection procedure.')}</p>}
    {model && !status.loading && !extras.safety && <>
      {coachSource(check) === 'rules' && <p className="lw-note is-info" role="note"><Info size={14} aria-hidden="true" />{t('AI feedback isn’t available right now, so these ideas come from simple writing checks. They can still help.')}</p>}
      <div className="lw-score">
        {scored ? <ScoreRing percent={model.overall} label={t('Depth score {n} of 100', { n: model.overall })} /> : <span className="lw-score-icon" aria-hidden="true"><Sparkles size={22} /></span>}
        <div>
          <strong>{scored ? t(headline(model.overall)) : t('Quick check')}</strong>
          <small>{delta !== null ? t('+{n} since last check', { n: delta }) : scored ? t('out of 100') : model.scoreHidden ? t(SCORE_HIDDEN_TEXT[model.scoreHidden]) : ''}</small>
        </div>
      </div>
      {Object.keys(model.scores).length > 0 && <ul className="lw-crit">
        {LETTER_CRITERIA.map(({ key, label, explain }) => {
          const value = Number(model.scores[key]) || 0
          const word = levelWord(value)
          const isOpen = openCriterion === key
          const count = open.filter((note) => note.criterion === key).length
          return <li key={key} className={`is-${key}`}>
            <button type="button" className="lw-crit-row" aria-expanded={isOpen} onClick={() => setOpenCriterion(isOpen ? null : key)}>
              <i aria-hidden="true" /><span className="lw-crit-name">{t(label)}</span>
              <span className="lw-crit-level">{word ? t(word) : ''}</span>
              <span className="lw-crit-bar" role="img" aria-label={word ? t('{label}: {value} of 4, {band}', { label: t(label), value, band: t(word) }) : t(label)}><span style={{ width: `${Math.max(0, Math.min(4, value)) * 25}%` }} /></span>
            </button>
            {isOpen && <p className="lw-crit-explain">{t(explain)}{count > 0 && !locked ? ` ${count === 1 ? t('1 note') : tp('{n} notes', count, { n: count })}` : ''}</p>}
          </li>
        })}
      </ul>}
      {scored && model.overall <= 50 && <section className="lw-big">
        <h3>{t('Big picture first')}</h3>
        {model.summary && <p className="lw-big-summary">{model.summary}</p>}
        {model.suggestions.length > 0 && <ol>{model.suggestions.map((text, index) => <li key={index}><span aria-hidden="true">{index + 1}</span>{text}</li>)}</ol>}
      </section>}
      {!(scored && model.overall <= 50) && model.summary && <p className="lw-summary">{model.summary}</p>}

      {extras.copy && <p className="lw-note is-info" role="note"><Copy size={14} aria-hidden="true" />{t('{n}% of this letter matches your letter of {date}. Only you see this.', { n: extras.copy.percent, date: formatDateLocale(extras.copy.date) })}</p>}
      {extras.sensitive.length > 0 && <>
        <div className="lw-sec"><h3>{t('Sensitive content')}</h3><span>{t('Not scored')}</span></div>
        <div className="lw-notes">{extras.sensitive.map((note) => <ExtraCard key={note.id} note={note} label={t(note.kind === 'health' ? 'Health' : 'Disciplinary matter')} active={note.id === activeId} onJump={onJump} />)}</div>
      </>}
      {extras.readerNotes.length > 0 && <>
        <div className="lw-sec"><h3>{t('How a reader may read this')}</h3><span>{t('Not scored')}</span></div>
        <div className="lw-notes">{extras.readerNotes.map((note) => <ExtraCard key={note.id} note={note} label={t('Reader note')} active={note.id === activeId} onJump={onJump} />)}</div>
      </>}

      {locked ? (scored && model.overall <= 50 ? null : <p className="lw-note">{t('Work on the big picture first.')}</p>) : <>
        <div className="lw-sec"><h3>{t('Notes')}</h3><span>{open.length ? tp('{n} to go', open.length, { n: open.length }) : ''}</span></div>
        {chips.length > 1 && <div className="lw-chips" role="group" aria-label={t('Filter notes')}>
          <button type="button" className={`lw-pill${activeFilter === 'all' ? ' is-on' : ''}`} aria-pressed={activeFilter === 'all'} onClick={() => setFilter('all')}>{t('All')} <b>{open.length}</b></button>
          {chips.map((chip) => <button key={chip.key} type="button" className={`lw-pill is-${chip.key}${activeFilter === chip.key ? ' is-on' : ''}`} aria-pressed={activeFilter === chip.key} onClick={() => setFilter(chip.key)}><i aria-hidden="true" />{t(chip.label)} <b>{chip.count}</b></button>)}
        </div>}
        <div className="lw-notes">
          {shown.map((note, position) => {
            const snippet = note.question.split(/\s+/).slice(0, 6).join(' ')
            const active = note.id === activeId
            return <article key={note.id} data-note={note.id} className={`lw-note-card is-${note.criterion}${active ? ' is-active' : ''}`}>
              <div className="lw-note-top">
                <span className="lw-note-crit">{t(letterCriterionLabel(note.criterion))}</span>
                {note.priority && <span className="lw-flag">{t('Priority')}</span>}
                <span className="lw-grow" />
                <button type="button" className="lw-corner is-ok" aria-label={t('Mark note {n} as done: {text}', { n: position + 1, text: snippet })} title={t('Mark as done')} onClick={() => onSetState(note, 'done')}><Check size={16} aria-hidden="true" /></button>
                <button type="button" className="lw-corner" aria-label={t('Mark note {n} as not useful: {text}', { n: position + 1, text: snippet })} title={t('Not useful')} onClick={() => onSetState(note, 'dismissed')}><X size={16} aria-hidden="true" /></button>
              </div>
              <button type="button" className="lw-note-main" aria-pressed={active} onClick={() => onJump(note)}>
                <span className="lw-note-q">{note.question}</span>
                {note.context && <span className="lw-note-ctx">{note.context}</span>}
              </button>
            </article>
          })}
          {!shown.length && <p className="lw-note">{open.length ? t('Nothing in this group.') : t('All notes done.')}</p>}
        </div>
        {done.length > 0 && <div className="lw-done">
          <button type="button" className="lw-done-toggle" aria-expanded={showDone} onClick={() => setShowDone((value) => !value)}><Check size={15} aria-hidden="true" />{t('Done ({n})', { n: done.length })}<ChevronDown size={15} aria-hidden="true" /></button>
          {showDone && <ul>{done.map((note) => <li key={note.id}><span title={note.question}>{note.question}</span><button type="button" className="lw-link" onClick={() => onSetState(note, 'open')}><Undo2 size={13} aria-hidden="true" />{t('Undo')}</button></li>)}</ul>}
        </div>}
        {gone.length > 0 && <p className="lw-note lw-fine">{gone.length === 1 ? t('1 idea no longer matches your text') : tp('{n} ideas no longer match your text', gone.length, { n: gone.length })}</p>}
      </>}
    </>}
  </>
}

function CheckFooter({ check, model, status, anchored, states, changed, inputChanged, notice, empty, onCheck }) {
  const open = useMemo(() => openNotes(model?.notes, states, anchored), [model, states, anchored])
  const block = status.loading ? null : recheckBlock({ hasCheck: Boolean(check), openCount: open.length, changed, inputChanged })
  const errorCode = status.error?.code
  const footerError = errorCode === 'notes_open' || errorCode === 'too_small_change'
  const errorText = status.error ? t(ERROR_TEXT[errorCode] || status.error.message || 'Check couldn’t read this letter.') : ''
  const dailyLimit = Number(check?.daily_limit) > 0 ? Math.round(Number(check.daily_limit)) : DAILY_CHECKS
  const left = check?.checks_left !== null && check?.checks_left !== undefined && Number.isFinite(Number(check.checks_left)) ? Math.max(0, Number(check.checks_left)) : null
  let line = ''
  if (status.loading) line = t('Checking…')
  else if (footerError) line = errorText
  else if (notice === 'reused') line = t('Already checked — nothing changed')
  else if (block === 'notes_open') line = tp('Resolve {n} note to check again|Resolve {n} notes to check again', open.length, { n: open.length })
  else if (block === 'unchanged') line = t('Change the letter to check again')
  else if (check) line = inputChanged ? t('Details changed') : changed ? t('Letter changed') : t('Up to date')
  else if (empty) line = t('Write the letter first')
  // Only the check's own error says whether AI is on (`details.ai_available`); a provider failure stays retryable.
  const { unavailable, retry } = checkAvailability(status.error)
  const disabled = status.loading || (Boolean(block) && !retry) || empty
  return <div className="lw-foot-row">
    <div className="lw-foot-info">
      <b className={footerError ? 'is-error' : ''} role={footerError ? 'alert' : 'status'}>{line}</b>
      {left !== null && <small>{t('{n} left today', { n: Math.min(left, dailyLimit) })}</small>}
    </div>
    {!unavailable && <button type="button" className="cx-btn primary" disabled={disabled} aria-busy={status.loading} onClick={onCheck}>
      <RefreshCw size={14} aria-hidden="true" className={status.loading ? 'spin' : ''} />{retry ? t('Try again') : check ? t('Check again') : t('Check depth')}
    </button>}
    {errorText && !footerError && !status.loading && <p className="lw-foot-error" role="alert">{errorText}</p>}
  </div>
}

function IdeasFooter({ ai, onAsk }) {
  const out = ai.left !== null && ai.left <= 0
  if (ai.available === false && !out) return <div className="lw-foot-row"><p className="lw-foot-note">{t('AI ideas are off for this account. Ideas from the profile still appear above.')}</p></div>
  return <div className="lw-foot-row">
    <div className="lw-foot-info">
      <b>{ai.left !== null ? t('AI · {n} of {limit} today', { n: ai.left, limit: ai.limit }) : t('AI ideas')}</b>
      <small>{out ? t('Daily AI limit reached') : t('Only when you ask. Never automatic.')}</small>
    </div>
    <button type="button" className="cx-btn primary" disabled={ai.loading || out} aria-busy={ai.loading} onClick={onAsk}>
      <Sparkles size={14} aria-hidden="true" />{ai.loading ? t('Thinking…') : t('Get AI ideas')}
    </button>
  </div>
}

function LetterPanel({ tab, onTab, ideas, onInsertFact, onAskAi, name, checkState, onCheck, onJump, onSetState, words, empty }) {
  const { check, model, extras, status, noteStates, anchored, activeId, changed, inputChanged, notice } = checkState
  const openCount = useMemo(() => openNotes(model?.notes, noteStates, anchored).length, [model, noteStates, anchored])
  const tabs = [{ id: 'ideas', label: t('Ideas'), count: ideas.facts.length }, { id: 'check', label: t('Check'), count: model && !model.notesLocked ? openCount : 0 }]
  const onKey = (event, index) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]
    onTab(next.id)
    event.currentTarget.parentElement?.querySelector(`[data-tab="${next.id}"]`)?.focus()
  }
  return <section className="lw-panel" aria-label={t('Letter help')}>
    <div role="tablist" aria-label={t('Letter help')} className="lw-tabs">
      {tabs.map((item, index) => <button key={item.id} type="button" role="tab" data-tab={item.id} id={`lw-tab-${item.id}`} aria-selected={tab === item.id} aria-controls="lw-tabpanel" tabIndex={tab === item.id ? 0 : -1}
        className={tab === item.id ? 'is-on' : ''} onClick={() => onTab(item.id)} onKeyDown={(event) => onKey(event, index)}>{item.label}{item.count > 0 && <span className="lw-count">{item.count}</span>}</button>)}
    </div>
    <div className="lw-pbody" id="lw-tabpanel" role="tabpanel" aria-labelledby={`lw-tab-${tab}`}>
      {tab === 'ideas'
        ? <IdeasTab ideas={ideas} name={name} onInsertFact={onInsertFact} />
        : <CheckTab {...{ check, model, extras, name, status, anchored, activeId, onJump, onSetState, words }} states={noteStates} />}
    </div>
    <div className="lw-foot">
      {tab === 'ideas'
        ? <IdeasFooter ai={ideas.ai} onAsk={onAskAi} />
        : <CheckFooter {...{ check, model, status, anchored, changed, inputChanged, notice, empty, onCheck }} states={noteStates} />}
    </div>
  </section>
}

export default memo(LetterPanel)
