import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { locale, t, tp } from '../i18n.js'
import { essayLabApi } from './essayLabApi.js'
import { buildMonth, canGoNext, isValidStreak, progressPercent, shiftMonth, splitMonth } from './streakModel.js'

const utc = (year, month, day = 1) => new Date(Date.UTC(year, month - 1, day))
const format = (options, date) => new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', ...options }).format(date)

function FireDefs() {
  return <svg width="0" height="0" focusable="false" aria-hidden="true" style={{ position: 'absolute' }}>
    <defs>
      <linearGradient id="el-fire-out" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor="#e03a0b" /><stop offset=".6" stopColor="#ff7a1a" /><stop offset="1" stopColor="#ffb02e" /></linearGradient>
      <linearGradient id="el-fire-in" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor="#ff9a1f" /><stop offset="1" stopColor="#ffe066" /></linearGradient>
      <symbol id="el-fire-sym" viewBox="0 0 30 34">
        <path fill="url(#el-fire-out)" d="M15 1c1.2 5.2-1.6 8-4.6 11.2C7.5 15.3 5 18.4 5 23c0 5.2 4.2 9.5 10 9.5S25 28.2 25 23c0-3.4-1.6-6.1-3.4-8.2-.4 2.2-1.4 3.6-3 4.4 1-6-1-12.4-3.6-18.2Z" />
        <path fill="url(#el-fire-in)" d="M15 15c.6 3-1.8 4.6-3 6.8-1 1.8-.8 4.3.8 5.7A4.8 4.8 0 0 0 19 24.5c0-1.8-.9-3-1.8-4-.2.9-.7 1.5-1.4 1.8.4-2.7-.1-5.4-.8-7.3Z" />
      </symbol>
    </defs>
  </svg>
}

function Flame({ lit }) {
  return <div className={`el-streak-flame ${lit ? 'is-lit' : 'is-out'}`} aria-hidden="true">
    <svg width="30" height="34" viewBox="0 0 30 34">
      <path className="fire-out" fill="url(#el-fire-out)" d="M15 1c1.2 5.2-1.6 8-4.6 11.2C7.5 15.3 5 18.4 5 23c0 5.2 4.2 9.5 10 9.5S25 28.2 25 23c0-3.4-1.6-6.1-3.4-8.2-.4 2.2-1.4 3.6-3 4.4 1-6-1-12.4-3.6-18.2Z" />
      <path className="fire-in" fill="url(#el-fire-in)" d="M15 15c.6 3-1.8 4.6-3 6.8-1 1.8-.8 4.3.8 5.7A4.8 4.8 0 0 0 19 24.5c0-1.8-.9-3-1.8-4-.2.9-.7 1.5-1.4 1.8.4-2.7-.1-5.4-.8-7.3Z" />
    </svg>
  </div>
}

function dayLabel(cell, monthKey) {
  const { year, month } = splitMonth(monthKey)
  const date = format({ day: 'numeric', month: 'long' }, utc(year, month, cell.day))
  const status = {
    fire: t('goal met'),
    ember: t('some writing, under the goal'),
    none: t('no writing'),
    future: t('upcoming'),
  }[cell.state]
  return `${date}: ${status}${cell.isToday ? `, ${t('today')}` : ''}`
}

function Calendar({ monthKey, days, todayKey, busy }) {
  const weeks = buildMonth(monthKey, days, todayKey)
  const weekdays = Array.from({ length: 7 }, (_, index) => utc(2024, 1, 1 + index))
  return <div className="el-streak-cal" role="grid" aria-label={t('Writing days')} aria-busy={busy || undefined}>
    <div className="el-streak-row" role="row">
      {weekdays.map((date) => <div key={date.getUTCDay()} className="el-streak-wd" role="columnheader" aria-label={format({ weekday: 'long' }, date)}>
        <span aria-hidden="true">{format({ weekday: 'short' }, date)}</span>
      </div>)}
    </div>
    {weeks.map((week, row) => <div key={row} className="el-streak-row" role="row">
      {week.map((cell, column) => {
        if (!cell) return <div key={column} className="el-streak-d is-blank" role="gridcell" aria-hidden="true" />
        const label = dayLabel(cell, monthKey)
        const marked = cell.state === 'fire' || cell.state === 'ember'
        return <div key={column} role="gridcell" title={label} aria-label={label} aria-current={cell.isToday ? 'date' : undefined}
          className={`el-streak-d is-${cell.state === 'fire' ? 'on' : cell.state === 'ember' ? 'part' : cell.state}${cell.isToday ? ' is-today' : ''}`}>
          {marked && <svg aria-hidden="true" focusable="false"><use href="#el-fire-sym" /></svg>}
          <span aria-hidden="true">{cell.day}</span>
        </div>
      })}
    </div>)}
  </div>
}

function Skeleton() {
  return <section className="el-streak is-skeleton" aria-label={t('Writing streak')} aria-busy="true">
    <div className="el-streak-top"><span className="el-streak-skel is-icon" /><span className="el-streak-skel is-title" /></div>
    <span className="el-streak-skel is-calendar" />
    <span className="el-streak-skel is-line" />
  </section>
}

function StreakPanel({ signal }) {
  const [data, setData] = useState(null)
  const [state, setState] = useState('loading')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const latest = useRef(0)
  const hasData = useRef(false)

  const load = useCallback(async (month) => {
    const id = latest.current + 1
    latest.current = id
    setBusy(true)
    try {
      const result = await essayLabApi.streak(month)
      if (id !== latest.current) return
      if (!isValidStreak(result)) throw new Error('streak')
      hasData.current = true
      setData(result)
      setState('ready')
      setNotice('')
    } catch {
      if (id !== latest.current) return
      if (hasData.current) setNotice(t('Could not load that month.'))
      else setState('error')
    } finally {
      if (id === latest.current) setBusy(false)
    }
  }, [])

  const viewed = useRef('')
  viewed.current = data?.month || ''

  // The library list reloads after the student writes; a newer edit time means
  // a save has landed, so the streak is read again for the month being viewed.
  useEffect(() => {
    if (signal === null) return undefined
    load(viewed.current || undefined)
    return () => { latest.current += 1 }
  }, [signal, load])

  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible' && hasData.current) load(viewed.current) }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [load])

  if (signal === null || (state === 'loading' && !data)) return <><FireDefs /><Skeleton /></>
  if (state === 'error' && !data) {
    return <section className="el-streak is-quiet" aria-label={t('Writing streak')}>
      <p className="el-streak-sub" role="status">{t('Could not load your streak.')}</p>
      <button type="button" className="el-btn is-small" onClick={() => { setState('loading'); load(undefined) }}>{t('Try again')}</button>
    </section>
  }

  const { current, best, progress, goal, today, month, days } = data
  const lit = Boolean(progress.goal_met)
  const wordsToday = progress.words === 1 ? t('1 word today') : tp('{count} words today', progress.words, { count: progress.words })
  const goalText = t('Goal: {words} words, or {minutes} min of writing', { words: goal.words, minutes: goal.minutes })
  const { year, month: monthNumber } = splitMonth(month)
  return <section className="el-streak" aria-label={t('Writing streak')}>
    <FireDefs />
    <div className="el-streak-top">
      <Flame lit={lit} />
      <div>
        <div className="el-streak-count">{current}<small>{tp('day streak', current)}</small></div>
        <div className="el-streak-sub">{best === 1 ? t('Best: 1 day') : tp('Best: {count} days', best, { count: best })}</div>
      </div>
      <span className={`el-badge ${lit ? 'is-good' : 'is-warn'}`}>{lit ? t('Done today') : t('Not yet')}</span>
    </div>
    <div className="el-streak-cal-head">
      <button type="button" className="el-icon-btn is-small" aria-label={t('Previous month')} disabled={busy} onClick={() => load(shiftMonth(month, -1))}><ChevronLeft size={16} aria-hidden="true" /></button>
      <strong aria-live="polite">{format({ month: 'long', year: 'numeric' }, utc(year, monthNumber))}</strong>
      <button type="button" className="el-icon-btn is-small" aria-label={t('Next month')} disabled={busy || !canGoNext(month, today)} onClick={() => load(shiftMonth(month, 1))}><ChevronRight size={16} aria-hidden="true" /></button>
    </div>
    <Calendar monthKey={month} days={days} todayKey={today} busy={busy} />
    {notice && <p className="el-streak-sub" role="status">{notice}</p>}
    <div className="el-streak-legend">
      <span><i className="is-on" />{t('Fire: goal met')}</span>
      <span><i className="is-part" />{t('Ember: under the goal')}</span>
      <span><i />{t('No writing')}</span>
    </div>
    <div className="el-streak-bar" role="progressbar" aria-label={t('Today’s progress')} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={progressPercent(progress, goal)} aria-valuetext={`${wordsToday}. ${goalText}`}>
      <i style={{ width: `${progressPercent(progress, goal)}%` }} />
    </div>
    <div className="el-streak-foot"><span>{wordsToday}</span><span>{goalText}</span></div>
  </section>
}

// Students only. `signal` is null until the library has loaded, then the newest
// edit time, so the streak is fetched once and again after a save.
export default function StreakCard({ user, signal }) {
  if (user?.role !== 'student') return null
  return <StreakPanel signal={signal} />
}
