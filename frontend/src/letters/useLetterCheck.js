import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { t } from '../i18n.js'
import { applyNoteState, inputChangedSince, mergeNoteStates, noteStateUpdates, serverNotice, textFingerprint } from '../essayLab/coachModel.js'
import { errorCode } from '../essayLab/essayLabApi.js'
import { locateNotes, normalizeLetterCheck } from './letterModel.js'

// The Check tab's data: the latest check, its notes placed in the text, note states and one "Check again".
// Same rules as Essay Coach (coachModel.js): notes whose sentence is gone count as resolved, the
// "text changed" test is the local fingerprint, and nothing here polls.
export function useLetterCheck({ letterId, body, inputKey, synced, flush, letterRef, notify, onOpen }) {
  const [check, setCheck] = useState(null)
  const [status, setStatus] = useState({ loading: false, error: null })
  const [noteStates, setNoteStates] = useState({})
  const [currentInputHash, setCurrentInputHash] = useState(null)
  const [liveFingerprint, setLiveFingerprint] = useState(null)
  const [notice, setNotice] = useState(null)
  const [activeId, setActiveId] = useState(null)
  const hints = useRef(new Map())
  const inflight = useRef(new Set())
  const latest = useRef({})
  latest.current = { check, noteStates, notify, onOpen }

  const model = useMemo(() => normalizeLetterCheck(check), [check])
  const notes = model?.notes

  // The latest check, once per letter.
  useEffect(() => {
    if (!letterId) return undefined
    let alive = true
    api.latestLetterCheck(letterId).then((latestCheck) => {
      if (!alive || !latestCheck?.result) return
      setCheck(latestCheck)
      setNoteStates(latestCheck.note_states || {})
      setCurrentInputHash(latestCheck.current_input_hash || null)
    }, () => {})
    return () => { alive = false }
  }, [letterId])

  const located = useMemo(() => locateNotes(body, notes, hints.current), [body, notes])
  useEffect(() => { hints.current = new Map([...located].map(([id, range]) => [id, range.from])) }, [located])
  const anchored = useMemo(() => new Set(located.keys()), [located])

  const marks = useMemo(() => (notes || [])
    .filter((note) => located.has(note.id) && noteStates[note.id] !== 'done' && noteStates[note.id] !== 'dismissed')
    .map((note) => ({ id: note.id, criterion: note.criterion, ...located.get(note.id) })), [notes, located, noteStates])

  // "Text changed": the same fingerprint as the server, computed here.
  useEffect(() => {
    let alive = true
    textFingerprint(body).then((value) => { if (alive) setLiveFingerprint(value) }, () => {})
    return () => { alive = false }
  }, [body])
  const changed = Boolean(check) && liveFingerprint !== null && (!check.text_fingerprint || liveFingerprint !== check.text_fingerprint)

  // A 409 notice in the footer goes away once the counselor acts on it.
  useEffect(() => {
    setStatus((previous) => (previous.error && (previous.error.code === 'notes_open' || previous.error.code === 'too_small_change') ? { loading: false, error: null } : previous))
  }, [liveFingerprint, noteStates])

  // Title or relationship changed (and saved): one GET for the fresh input hash.
  const lastInput = useRef(inputKey)
  useEffect(() => {
    if (lastInput.current === inputKey || !synced) return undefined
    lastInput.current = inputKey
    if (!check?.id || !letterId) return undefined
    let alive = true
    api.latestLetterCheck(letterId).then((latestCheck) => {
      if (alive && latestCheck?.current_input_hash) setCurrentInputHash(latestCheck.current_input_hash)
    }, () => {})
    return () => { alive = false }
  }, [inputKey, synced, check?.id, letterId])
  const inputChanged = inputChangedSince(check, currentInputHash)

  // Notes whose sentence vanished become 'gone' (and reopen if it comes back): told to the server
  // once per check+note, only while the saved text is what is shown.
  const sent = useRef(new Map())
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!check?.id || !notes || !synced || !letterId) return undefined
    const checkId = check.id
    const timer = window.setTimeout(() => {
      for (const { id, state } of noteStateUpdates(notes, noteStates, anchored)) {
        const key = `${checkId}:${id}:${state}`
        const tries = sent.current.get(key) ?? 0
        if (tries < 0 || tries >= 3 || inflight.current.has(id)) continue
        sent.current.set(key, -1)
        if (state === 'gone') sent.current.delete(`${checkId}:${id}:open`)
        else sent.current.delete(`${checkId}:${id}:gone`)
        setNoteStates((previous) => applyNoteState(previous, id, state))
        api.setLetterNoteState(letterId, checkId, id, state).then(() => {
          sent.current.set(key, 99)
        }, () => {
          sent.current.set(key, tries + 1)
          setNoteStates((previous) => (state === 'gone' && previous[id] === 'gone' ? applyNoteState(previous, id, 'open') : state === 'open' && !previous[id] ? applyNoteState(previous, id, 'gone') : previous))
          window.setTimeout(() => setRetry((value) => value + 1), 3000 * (tries + 1))
        })
      }
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [check, notes, noteStates, anchored, synced, letterId, retry])

  const noticeTimer = useRef(null)
  useEffect(() => () => window.clearTimeout(noticeTimer.current), [])

  const runCheck = useCallback(async () => {
    setStatus({ loading: true, error: null })
    setNotice(null)
    latest.current.onOpen?.()
    try {
      let result
      for (let attempt = 0; attempt < 2 && !result; attempt += 1) {
        await flush({ force: attempt > 0 })
        const current = letterRef.current
        try {
          result = await api.letterDepthCheck(current.id, current.updated_at)
        } catch (error) {
          // "stale": the letter changed elsewhere. Save ours and retry once.
          if (error?.status !== 409 || attempt === 1 || serverNotice(error)) throw error
        }
      }
      setCheck(result)
      setNoteStates(result.note_states || {})
      setCurrentInputHash(result.current_input_hash || null)
      setActiveId(null)
      sent.current.clear()
      setStatus({ loading: false, error: null })
      if (result.reused) {
        setNotice('reused')
        window.clearTimeout(noticeTimer.current)
        noticeTimer.current = window.setTimeout(() => setNotice(null), 4000)
      }
    } catch (error) {
      if (serverNotice(error) === 'notes_open' && letterRef.current?.id) {
        sent.current.clear()
        api.latestLetterCheck(letterRef.current.id).then((latestCheck) => {
          if (!latestCheck?.result) return
          setCheck(latestCheck)
          setNoteStates((previous) => mergeNoteStates(latestCheck.note_states, previous, inflight.current))
        }, () => {})
      }
      setStatus({ loading: false, error: { code: serverNotice(error) || errorCode(error) || (error?.status === 409 ? 'stale' : null), message: error?.message } })
    }
  }, [flush, letterRef])

  // state: 'done' | 'dismissed' | 'open'. Applied at once, saved, rolled back when it fails.
  const setNoteState = useCallback((note, state) => {
    const { check: current, noteStates: states } = latest.current
    const checkId = current?.id
    const id = letterRef.current?.id
    if (!checkId || !id || inflight.current.has(note.id)) return
    const before = states[note.id] || 'open'
    if (before === state) return
    setNoteStates((previous) => applyNoteState(previous, note.id, state))
    if (state !== 'open') setActiveId((value) => (value === note.id ? null : value))
    inflight.current.add(note.id)
    api.setLetterNoteState(id, checkId, note.id, state).then(() => {
      inflight.current.delete(note.id)
    }, () => {
      inflight.current.delete(note.id)
      if (latest.current.check?.id !== checkId) return
      setNoteStates((previous) => applyNoteState(previous, note.id, before))
      latest.current.notify(t('Could not save that. Try again.'), 'error')
    })
  }, [letterRef])

  return { check, model, status, noteStates, notice, changed, inputChanged, located, anchored, marks, activeId, setActiveId, runCheck, setNoteState }
}
