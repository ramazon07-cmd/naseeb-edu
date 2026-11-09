// Pure helpers for the writing-streak card. Dates are 'YYYY-MM-DD' strings and
// months 'YYYY-MM' strings exactly as the server sends them; the browser clock
// is never read, so "today" is always the server's (Tashkent) day.

const pad = (value) => String(value).padStart(2, '0')

export function splitMonth(monthKey) {
  const [year, month] = String(monthKey).split('-').map(Number)
  return { year, month }
}

export const monthOf = (dateKey) => String(dateKey).slice(0, 7)

export function shiftMonth(monthKey, delta) {
  const { year, month } = splitMonth(monthKey)
  const index = year * 12 + (month - 1) + delta
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`
}

export const canGoNext = (monthKey, todayKey) => monthKey < monthOf(todayKey)

export const daysInMonth = (monthKey) => {
  const { year, month } = splitMonth(monthKey)
  return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

// Monday first: 0 = Monday ... 6 = Sunday.
export const firstWeekday = (monthKey) => {
  const { year, month } = splitMonth(monthKey)
  return (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7
}

export function dayState(dateKey, days, todayKey) {
  if (dateKey > todayKey) return 'future'
  const mark = days?.[dateKey]
  return mark === 'fire' || mark === 'ember' ? mark : 'none'
}

// Weeks of 7 cells, Monday first. A cell is null before the 1st and after the last day.
export function buildMonth(monthKey, days, todayKey) {
  const cells = Array.from({ length: firstWeekday(monthKey) }, () => null)
  for (let day = 1; day <= daysInMonth(monthKey); day += 1) {
    const key = `${monthKey}-${pad(day)}`
    cells.push({ key, day, state: dayState(key, days, todayKey), isToday: key === todayKey })
  }
  while (cells.length % 7) cells.push(null)
  const weeks = []
  for (let index = 0; index < cells.length; index += 7) weeks.push(cells.slice(index, index + 7))
  return weeks
}

export function progressPercent(progress, goal) {
  const words = goal?.words ? (progress?.words || 0) / goal.words : 0
  const minutes = goal?.minutes ? (progress?.minutes || 0) / goal.minutes : 0
  return Math.max(0, Math.min(100, Math.round(Math.max(words, minutes) * 100)))
}

// The newest edit time in the list: it changes once a save has landed, which is
// when the streak is worth fetching again.
export function latestEdit(essays) {
  let latest = ''
  for (const essay of essays || []) {
    const stamp = essay?.last_edited_at || essay?.updated_at || ''
    if (stamp > latest) latest = stamp
  }
  return latest
}

export function isValidStreak(data) {
  return Boolean(data)
    && typeof data.today === 'string'
    && Number.isFinite(data.current)
    && Number.isFinite(data.best)
    && typeof data.month === 'string'
    && data.progress != null
    && data.goal != null
}
