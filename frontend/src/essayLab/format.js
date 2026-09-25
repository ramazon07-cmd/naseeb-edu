// Small date and word helpers for the Essay Lab, in the interface language.
import { formatDateLocale, locale, t, tp } from '../i18n.js'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

function startOfDay(date) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy.getTime()
}

export function relativeTime(iso, now = Date.now()) {
  if (!iso) return ''
  const time = Date.parse(iso)
  if (!Number.isFinite(time)) return ''
  const diff = Math.max(0, now - time)
  if (diff < 45_000) return t('just now')
  if (diff < HOUR) return t('{n} min ago', { n: Math.max(1, Math.round(diff / MINUTE)) })
  const days = Math.round((startOfDay(now) - startOfDay(time)) / DAY)
  if (days === 0) return t('{n} h ago', { n: Math.round(diff / HOUR) })
  if (days === 1) return t('yesterday')
  if (days < 7) return tp('{n} days ago', days, { n: days })
  if (days < 14) return t('last week')
  return dayMonth(new Date(time))
}

const clock = (date) => date.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', hour12: false })
const dayMonth = (date) => formatDateLocale(date, { day: 'numeric', month: 'short' })
const weekday = (date, style) => date.toLocaleDateString(locale(), { weekday: style })

// "today at 21:14", "yesterday at 09:02", "on Tuesday at 21:14", "on 12 Sep at 18:00"
export function whenWritten(iso, now = Date.now()) {
  const time = Date.parse(iso || '')
  if (!Number.isFinite(time)) return ''
  const date = new Date(time)
  const days = Math.round((startOfDay(now) - startOfDay(time)) / DAY)
  if (days <= 0) return t('today at {time}', { time: clock(date) })
  if (days === 1) return t('yesterday at {time}', { time: clock(date) })
  if (days < 7) return t('on {day} at {time}', { day: weekday(date, 'long'), time: clock(date) })
  return t('on {day} at {time}', { day: dayMonth(date), time: clock(date) })
}

export function shortTime(iso) {
  const time = Date.parse(iso || '')
  if (!Number.isFinite(time)) return ''
  return clock(new Date(time))
}

export function dayGroup(iso, now = Date.now()) {
  const time = Date.parse(iso || '')
  if (!Number.isFinite(time)) return 'Earlier'
  const days = Math.round((startOfDay(now) - startOfDay(time)) / DAY)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return 'Earlier'
}

export function checkpointDate(iso, now = Date.now()) {
  const time = Date.parse(iso || '')
  if (!Number.isFinite(time)) return ''
  const date = new Date(time)
  const days = Math.round((startOfDay(now) - startOfDay(time)) / DAY)
  if (days <= 1) return clock(date)
  if (days < 7) return `${weekday(date, 'short')} ${clock(date)}`
  return dayMonth(date)
}


export const STATUS_LABELS = {
  draft: 'Draft',
  reviewing: 'With counselor',
  needs_revision: 'Needs revision',
  approved: 'Approved',
}
