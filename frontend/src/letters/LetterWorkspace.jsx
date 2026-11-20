import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Check, ChevronDown, ChevronLeft, Loader2 } from 'lucide-react'
import { api } from '../api.js'
import { formatNumberLocale, t, tp, tx } from '../i18n.js'
import { dateText, gradeText } from '../lib/format.js'
import { fullName, label } from '../lib/labels.js'
import { Field } from '../components/forms.jsx'
import { StudentReviewNote } from '../components/RecommendationLetters.jsx'
import { createIdeasController, initialIdeasState } from './ideasController.js'
import { factLine, fillStudent, inputKeyOf, insertAtCaret, wordCount } from './letterModel.js'
import { LetterSheet } from './LetterSheet.jsx'
import LetterPanel from './LetterPanel.jsx'
import { useLetterCheck } from './useLetterCheck.js'
import './letters.css'

const STATUSES = ['requested', 'drafting', 'submitted', 'approved']
const AUTOSAVE_MS = 2000
const FORM_KEYS = ['recommender_name', 'recommender_title', 'relationship', 'deadline', 'status', 'body', 'shared_with_student']

const sameForm = (a, b) => FORM_KEYS.every((key) => a[key] === b[key])

function useLetterIdeas(studentId, form) {
  const [state, setState] = useState(initialIdeasState)
  const controller = useRef(null)
  const context = { draft: form.body, recommender_title: form.recommender_title, relationship: form.relationship }
  const latest = useRef(context)
  latest.current = context
  useEffect(() => {
    const next = createIdeasController({
      load: (payload) => api.letterSuggestions({ student: studentId, ...payload }),
      onChange: setState,
    })
    controller.current = next
    next.start(latest.current)
    return () => next.dispose()
  }, [studentId])
  useEffect(() => { controller.current?.update(context) }, [form.body, form.recommender_title, form.relationship]) // eslint-disable-line react-hooks/exhaustive-deps
  const askAi = useCallback(() => controller.current?.askAi(), [])
  return { ideas: state, askAi }
}

function SaveStatus({ state, error }) {
  if (state === 'saving') return <span className="lw-saved" role="status"><Loader2 size={14} className="spin" aria-hidden="true" />{t('Saving…')}</span>
  if (state === 'error') return <span className="lw-saved is-error" role="alert"><AlertCircle size={14} aria-hidden="true" />{error || t('Not saved')}</span>
  if (state === 'dirty') return <span className="lw-saved" role="status">{t('Unsaved changes')}</span>
  return <span className="lw-saved is-ok" role="status"><Check size={14} aria-hidden="true" />{t('Saved')}</span>
}

function LetterEditor({ student, user, initialLetter, onBack, onOpened, onSaved, notify }) {
  const initial = useMemo(() => ({
    recommender_name: initialLetter?.recommender_name ?? fullName(user),
    recommender_title: initialLetter?.recommender_title ?? (user.position || ''),
    relationship: initialLetter?.relationship ?? '',
    deadline: initialLetter?.deadline ?? '',
    status: initialLetter?.status ?? 'drafting',
    body: initialLetter?.body ?? '',
    shared_with_student: initialLetter?.shared_with_student ?? false,
  }), []) // eslint-disable-line react-hooks/exhaustive-deps
  const [form, setForm] = useState(initial)
  const [letter, setLetter] = useState(initialLetter)
  const [savedForm, setSavedForm] = useState(initialLetter ? initial : null)
  const [save, setSave] = useState({ saving: false, error: '' })
  const [tab, setTab] = useState('ideas')
  const [details, setDetails] = useState(!initialLetter)
  const formRef = useRef(form)
  formRef.current = form
  const savedRef = useRef(savedForm)
  const letterRef = useRef(initialLetter)
  const chain = useRef(null)
  const callbacks = useRef({ onSaved, onOpened })
  callbacks.current = { onSaved, onOpened }
  const sheet = useRef(null)
  const panelRef = useRef(null)
  const first = student.user_detail?.first_name || fullName(student.user_detail)
  const name = fullName(student.user_detail)

  const isDirty = useCallback(() => !savedRef.current || !sameForm(formRef.current, savedRef.current), [])
  const dirty = !savedForm || !sameForm(form, savedForm)

  const saveOnce = useCallback(async () => {
    const snapshot = formRef.current
    const payload = { ...snapshot, deadline: snapshot.deadline || null }
    const current = letterRef.current
    setSave({ saving: true, error: '' })
    try {
      const saved = current ? await api.update('recommendations', current.id, payload) : await api.create('recommendations', { ...payload, student: student.id })
      letterRef.current = saved
      savedRef.current = snapshot
      setLetter(saved)
      setSavedForm(snapshot)
      setSave({ saving: false, error: '' })
      callbacks.current.onSaved(saved)
      if (!current) callbacks.current.onOpened(saved)
    } catch (error) {
      setSave({ saving: false, error: error.message })
      throw error
    }
  }, [student.id])

  // One save at a time; anything typed meanwhile goes in the next one. `force` saves even when nothing
  // changed (a stale check wants a fresh updated_at).
  const flush = useCallback(async ({ force = false } = {}) => {
    while (chain.current) {
      try { await chain.current } catch { /* its caller shows the error */ }
    }
    if (!force && !isDirty()) return
    chain.current = (async () => { try { await saveOnce() } finally { chain.current = null } })()
    await chain.current
    if (isDirty()) await flush()
  }, [saveOnce, isDirty])

  // Autosave after a pause: the same PATCH as the Save button. A new letter is created once it has text.
  useEffect(() => {
    if (!dirty || (!letterRef.current && !form.body.trim())) return undefined
    const timer = window.setTimeout(() => { flush().catch(() => {}) }, AUTOSAVE_MS)
    return () => window.clearTimeout(timer)
  }, [form, dirty, flush])

  const set = (key) => (event) => {
    const { value } = event.target
    setForm((current) => ({ ...current, [key]: value }))
  }
  const setBody = useCallback((body) => setForm((current) => ({ ...current, body })), [])
  const toggleShare = () => {
    setForm((current) => ({ ...current, shared_with_student: !current.shared_with_student }))
    window.setTimeout(() => { flush().catch(() => {}) }, 0)
  }

  const saveState = save.saving ? 'saving' : save.error ? 'error' : dirty ? 'dirty' : 'saved'
  const synced = saveState === 'saved' && Boolean(letter?.id)
  const words = wordCount(form.body)

  const checkState = useLetterCheck({
    letterId: letter?.id ?? null, body: form.body, inputKey: inputKeyOf(form), synced, flush, letterRef, notify, onOpen: () => setTab('check'),
  })
  const ideasState = useLetterIdeas(student.id, form)

  function insert(text) {
    if (!text) return
    const [start, end] = sheet.current?.selection() || [form.body.length, form.body.length]
    const result = insertAtCaret(formRef.current.body, start, end, text)
    if (!result) { notify(t('The letter is at its length limit.'), 'error'); return }
    setBody(result.body)
    sheet.current?.caretTo(result.caret)
  }

  const { located, setActiveId } = checkState
  const jump = useCallback((note) => {
    setActiveId(note.id)
    sheet.current?.reveal(located.get(note.id), note.id)
  }, [located, setActiveId])
  const noteClicked = useCallback((id) => {
    setActiveId(id)
    setTab('check')
    window.requestAnimationFrame(() => panelRef.current?.querySelector(`[data-note="${CSS.escape(String(id))}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }, [setActiveId])

  async function back() {
    if (save.saving || dirty) {
      try { await flush() } catch {
        if (!window.confirm(t('Discard your changes to this letter?'))) return
      }
    }
    onBack()
  }

  const summaryParts = [form.recommender_name, form.recommender_title, form.deadline && tx`due ${dateText(form.deadline)}`, label(form.status)].filter(Boolean)

  return <div className="lw">
    <header className="lw-top">
      <div className="lw-row1">
        <button type="button" className="lw-back" onClick={back} aria-label={t('Back to letters')}><ChevronLeft size={18} aria-hidden="true" /></button>
        <div className="lw-title"><span className="lw-eyebrow">{t('Recommendation letter')}</span><h1>{tx`For ${name}`}</h1></div>
        <span className="lw-grow" />
        <SaveStatus state={saveState} error={save.error} />
        {(saveState === 'dirty' || saveState === 'error') && <button type="button" className="cx-btn" onClick={() => flush().then(() => notify(t('Letter saved.'))).catch(() => {})}>{t('Save')}</button>}
        <button type="button" role="switch" aria-checked={form.shared_with_student} className="lw-switch" onClick={toggleShare} aria-describedby="lw-share-note">
          <span className="lw-sw" aria-hidden="true" /><b>{t('Show to student')}</b>
        </button>
      </div>
      <div className="lw-row2">
        <button type="button" className="lw-meta" aria-expanded={details} aria-controls="lw-details" onClick={() => setDetails((value) => !value)}>
          <span>{summaryParts.map((part, index) => <span key={index}>{index > 0 && ' · '}{index === 0 ? <b>{part}</b> : part}</span>)}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        <p id="lw-share-note" className="lw-share-note">{form.shared_with_student ? t('The student can read the letter.') : t('The student sees who writes the letter and its status, but not the text.')}</p>
        {details && <div className="lw-details" id="lw-details">
          <Field label="Recommender name"><input value={form.recommender_name} onChange={set('recommender_name')} required maxLength={180} /></Field>
          <Field label="Position"><input value={form.recommender_title} onChange={set('recommender_title')} maxLength={180} placeholder={t('e.g. School counselor')} /></Field>
          <Field label="Deadline"><input type="date" value={form.deadline} onChange={set('deadline')} /></Field>
          <Field label="Status"><select value={form.status} onChange={set('status')}>{STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></Field>
          <Field label="How you know the student"><input value={form.relationship} onChange={set('relationship')} maxLength={180} placeholder={t('e.g. Counselor since grade 9')} /></Field>
        </div>}
      </div>
    </header>
    <div className="lw-work">
      <main className="lw-stage">
        <StudentReviewNote letter={letter} name={first} />
        <LetterSheet ref={sheet} body={form.body} onBody={setBody} marks={checkState.marks} activeId={checkState.activeId} located={checkState.located} onNoteClick={noteClicked}
          header={<div className="lw-sheet-meta"><span>{[tx`Recommendation for ${name}`, gradeText(student.grade)].filter(Boolean).join(', ')}</span><span>{form.recommender_name}</span></div>} />
        <p className="lw-words">{tp('{n} word|{n} words', words, { n: formatNumberLocale(words) })}</p>
      </main>
      <div className="lw-side" ref={panelRef}>
        <LetterPanel tab={tab} onTab={setTab} ideas={ideasState.ideas} name={first} onAskAi={ideasState.askAi}
          onInsertFact={(fact) => insert(factLine(fact))} onInsertIdea={(item) => insert(fillStudent(item.text, first))}
          checkState={checkState} onCheck={checkState.runCheck} onJump={jump} onSetState={checkState.setNoteState} words={words} empty={!form.body.trim()} />
      </div>
    </div>
  </div>
}

// The full-page letter workspace: /students/<id>/letters/new or /letters/<letterId>.
export function LetterWorkspace({ student, user, letterId, onBack, onOpened, onSaved, notify }) {
  const isNew = letterId === 'new'
  const [loaded, setLoaded] = useState({ state: isNew ? 'ready' : 'loading', letter: null, error: '' })
  const [attempt, setAttempt] = useState(0)
  const current = useRef(null) // id of the letter the editor holds
  useEffect(() => {
    if (isNew || current.current === letterId) return undefined
    let alive = true
    setLoaded({ state: 'loading', letter: null, error: '' })
    api.retrieve('recommendations', letterId).then((letter) => {
      if (!alive) return
      if (letter.student !== student.id) setLoaded({ state: 'error', letter: null, error: t('Recommendation letter not found.') })
      else { current.current = letter.id; setLoaded({ state: 'ready', letter, error: '' }) }
    }, (error) => { if (alive) setLoaded({ state: 'error', letter: null, error: error.status === 404 ? t('Recommendation letter not found.') : error.message }) })
    return () => { alive = false }
  }, [letterId, isNew, student.id, attempt])

  const opened = useCallback((saved) => { current.current = saved.id; onOpened(saved.id) }, [onOpened])

  if (loaded.state === 'loading') return <div className="lw lw-state"><p className="cx-empty" role="status">{t('Loading recommendation letters…')}</p></div>
  if (loaded.state === 'error') return <div className="lw lw-state">
    <button type="button" className="cx-back" onClick={onBack}><ChevronLeft size={16} aria-hidden="true" /><b>{t('Back to letters')}</b></button>
    <div className="alert error" role="alert">{loaded.error} <button type="button" className="cx-btn" onClick={() => setAttempt((n) => n + 1)}>{t('Retry')}</button></div>
  </div>
  return <LetterEditor key={student.id} {...{ student, user, onBack, onSaved, notify }} initialLetter={loaded.letter} onOpened={opened} />
}
