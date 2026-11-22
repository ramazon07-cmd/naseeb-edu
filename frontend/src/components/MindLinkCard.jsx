import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, ExternalLink, Link2, RefreshCw } from 'lucide-react';
import { api } from '../api';
import { formatDateLocale, getLanguage, t } from '../i18n';
import { becameLinked, isCodeExpired, majorOffer, mindCardState, shouldCheckOnFocus, startMindLink } from '../lib/mindLink';

// "Bring my Naseeb Mind results". One status request when the page opens, one on "Check again" and one
// when the student returns to this tab while a link is waiting; never a timer.
export function MindLinkCard({ student, notify, reload, onLinked }) {
  const [status, setStatus] = useState(null)
  const [waiting, setWaiting] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [mindUrl, setMindUrl] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [expired, setExpired] = useState(false)
  const alive = useRef(true)
  const last = useRef({ at: 0, waiting: false, linked: null, expiresAt: '' })

  const refresh = useCallback(async () => {
    last.current.at = Date.now()
    try {
      const next = await api.mindLinkStatus()
      if (!alive.current) return null
      setStatus(next)
      if (next.linked) {
        setWaiting(false)
        setMindUrl('')
        if (becameLinked(last.current.linked, next.linked)) onLinked?.()
      }
      last.current.linked = Boolean(next.linked)
      return next
    } catch {
      return null
    }
  }, [onLinked])

  useEffect(() => {
    alive.current = true
    refresh()
    return () => { alive.current = false }
  }, [refresh])

  useEffect(() => { last.current.waiting = waiting; last.current.expiresAt = expiresAt }, [waiting, expiresAt])
  // One-shot (not a poll, no request): when the code's time is up the card stops waiting for it.
  useEffect(() => {
    if (!waiting || !expiresAt) return undefined
    const left = new Date(expiresAt).getTime() - Date.now()
    if (!Number.isFinite(left)) return undefined
    if (left <= 0) { setExpired(true); return undefined }
    const timer = setTimeout(() => setExpired(true), Math.min(left, 2147483647))
    return () => clearTimeout(timer)
  }, [waiting, expiresAt])
  useEffect(() => {
    const onFocus = () => {
      if (isCodeExpired(last.current.expiresAt)) setExpired(true)
      if (shouldCheckOnFocus({ waiting: last.current.waiting, lastCheckAt: last.current.at, now: Date.now() })) refresh()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refresh])

  const state = mindCardState(status, { waiting, expired })
  if (state === 'hidden') return null

  const start = async () => {
    setBusy('start')
    setError('')
    try {
      const { url, expiresAt: until } = await startMindLink({ start: (lang) => api.startMindLink(lang), lang: getLanguage() })
      setMindUrl(url)
      setExpiresAt(until || '')
      setExpired(false)
      setWaiting(true)
    } catch (requestError) {
      // Someone already linked (another tab): show the real state.
      if (requestError?.status === 409) await refresh()
      else setError(t('Could not start the link. Try again.'))
    } finally {
      setBusy('')
    }
  }
  const check = async () => {
    setBusy('check')
    setError('')
    const next = await refresh()
    if (!next) setError(t('Could not check the link. Try again.'))
    else if (!next.linked) setError(t('Not linked yet.'))
    setBusy('')
  }
  const stop = async () => {
    setBusy('stop')
    setError('')
    try {
      setStatus(await api.stopMindLink())
      last.current.linked = false
      notify?.(t('Sharing stopped. Results already imported stay here.'))
    } catch {
      setError(t('Could not stop sharing. Try again.'))
    } finally {
      setBusy('')
    }
  }
  const offered = majorOffer(status, student)
  const useMajor = async () => {
    setBusy('major')
    setError('')
    try {
      await api.update('students', student.id, { target_major: offered })
      notify?.(t('{major} saved as your study direction.', { major: t(offered) }))
      reload?.()
      refresh()
    } catch {
      setError(t('Could not save your major. Try again.'))
    } finally {
      setBusy('')
    }
  }

  return <div className="nb-mf-card nb-mf-mindlink" data-state={state}>
    {state === 'linked'
      ? <>
        <p className="eyebrow"><CheckCircle2 size={14} aria-hidden="true" /> {t('Naseeb Mind linked')}</p>
        <p>{status.linked_at ? t('Linked on {date}', { date: formatDateLocale(status.linked_at) }) : ''}{status.linked_at ? ' · ' : ''}{status.last_sync_at ? t('Last sync {date}', { date: formatDateLocale(status.last_sync_at) }) : t('No results received yet')}</p>
        <p className="nb-mf-mindlink-note">{t('Results already imported stay in your profile here.')}</p>
        {offered && <div className="nb-mf-mindlink-major">
          <span>{t('In Naseeb Mind you chose {major}.', { major: t(offered) })}</span>
          <button type="button" className="nb-mf-start" onClick={useMajor} disabled={busy === 'major'}>{t('Use as my major')}</button>
        </div>}
        <button type="button" className="nb-mf-mindlink-quiet" onClick={stop} disabled={busy === 'stop'}>{busy === 'stop' ? t('Stopping…') : t('Stop sharing')}</button>
      </>
      : <>
        <p className="eyebrow">{t('Naseeb Mind')}</p>
        <h3>{t('Bring my Naseeb Mind results')}</h3>
        {state === 'expired'
          ? <>
            <p>{t('The link code expired. Start again to get a new one.')}</p>
            <button type="button" className="nb-mf-start" onClick={start} disabled={busy === 'start'}><Link2 size={15} aria-hidden="true" />{busy === 'start' ? t('Opening…') : t('Start again')}</button>
          </>
          : state === 'waiting'
          ? <>
            <p>{t('Naseeb Mind opened in a new tab. Share your results there, then come back and check.')}</p>
            {mindUrl && <a className="nb-mf-mindlink-quiet" href={mindUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} aria-hidden="true" /> {t('Open Naseeb Mind')}</a>}
            <button type="button" className="nb-mf-start" onClick={check} disabled={busy === 'check'}><RefreshCw size={15} aria-hidden="true" />{t('Check again')}</button>
          </>
          : <>
            <p>{t('Already took the tests on naseebmind.uz? Link your account once and your results appear here, and new ones follow on their own.')}</p>
            <button type="button" className="nb-mf-start" onClick={start} disabled={busy === 'start'}><Link2 size={15} aria-hidden="true" />{busy === 'start' ? t('Opening…') : t('Connect Naseeb Mind')}</button>
          </>}
      </>}
    {error && <p className="nb-mf-error" role="alert">{error}</p>}
  </div>
}
