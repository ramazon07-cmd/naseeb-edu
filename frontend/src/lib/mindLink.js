// Naseeb Mind -> Naseeb Edu link, student side. Pure helpers: no timers, no polling. The card asks the
// server for the status once when it opens, when the student presses "Check again", and when they
// come back to this tab after opening Naseeb Mind (window focus).
import { closeWindow, navigateWindow, openBlankWindow } from './telegramLink.js'

// hidden: the feature is off (or the status is unknown); idle: can start; waiting: the link was opened in
// Mind, the student comes back to check; linked: results are being shared.
// expired: the 10-minute code ran out while waiting; the card offers "Start again" (a new code).
export function mindCardState(status, { waiting = false, expired = false } = {}) {
  if (!status || !status.available) return 'hidden'
  if (status.linked) return 'linked'
  if (!waiting) return 'idle'
  return expired ? 'expired' : 'waiting'
}

// True once the code's expires_at has passed (unknown or unparsable: not expired, the server decides).
export function isCodeExpired(expiresAt, now = Date.now()) {
  const at = expiresAt ? new Date(expiresAt).getTime() : NaN
  return Number.isFinite(at) && now >= at
}

// Opens the blank tab first (still inside the click, so it is not taken for a pop-up), asks for the code,
// then sends the tab to Naseeb Mind. `url` comes back too, for the plain link when the browser blocked the tab.
export async function startMindLink({ start, lang, open = openBlankWindow, navigate = navigateWindow, close = closeWindow }) {
  const win = open()
  try {
    const { url, expires_at: expiresAt } = await start(lang)
    return { url, expiresAt, opened: navigate(win, url) }
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

// The linked-callback fires only on a real not-linked -> linked change seen during this mount. `previous` is
// null until the first status arrives, so a student who was already linked (e.g. remounting after "Review
// answers") never triggers a reload that would overwrite unfinished edits.
export const becameLinked = (previous, next) => previous === false && Boolean(next)
