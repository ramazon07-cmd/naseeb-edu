// Naseeb Mind -> Naseeb Edu link, student side. Pure helpers: no timers, no polling. The card asks the
// server for the status once when it opens, when the student presses "Check again", and when they
// come back to this tab after opening Naseeb Mind (window focus).
import { closeWindow, navigateWindow, openBlankWindow } from './telegramLink.js'

// hidden: the feature is off (or the status is unknown); idle: can start; waiting: the link was opened in
// Mind, the student comes back to check; linked: results are being shared.
export function mindCardState(status, { waiting = false } = {}) {
  if (!status || !status.available) return 'hidden'
  if (status.linked) return 'linked'
  return waiting ? 'waiting' : 'idle'
}

// Opens the blank tab first (still inside the click, so it is not taken for a pop-up), asks for the code,
// then sends the tab to Naseeb Mind. `url` comes back too, for the plain link when the browser blocked the tab.
export async function startMindLink({ start, lang, open = openBlankWindow, navigate = navigateWindow, close = closeWindow }) {
  const win = open()
  try {
    const { url } = await start(lang)
    return { url, opened: navigate(win, url) }
  } catch (error) {
    close(win)
    throw error
  }
}

// A returning visit to the tab re-checks only while a link is waiting, and not more than once every few seconds.
export function shouldCheckOnFocus({ waiting, lastCheckAt = 0, now, minGapMs = 4000 }) {
  return Boolean(waiting) && now - lastCheckAt >= minGapMs
}

// Attempts answered under another instrument version are shown, marked, and kept out of every comparison
// and of the "current result" for their challenge.
export const isMismatched = (row) => Boolean(row && row.source_version_mismatch)

// The newest comparable attempt per challenge (the API lists newest first).
export function latestComparable(rows) {
  const latest = {}
  for (const row of rows) if (!isMismatched(row) && !latest[row.challenge]) latest[row.challenge] = row
  return latest
}

export const mismatchedAttempts = (rows) => rows.filter(isMismatched)

// The major chosen in Naseeb Mind is offered only while the student has none; never applied by itself.
export function majorOffer(status, student) {
  const offered = (status?.chosen_major || '').trim()
  if (!offered || !student || (student.target_major || '').trim()) return ''
  return offered
}
