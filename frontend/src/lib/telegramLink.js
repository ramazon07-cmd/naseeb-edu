// Connecting a student's Telegram with one tap: the site asks for a one-time bot link, opens it, and
// then watches the account until the bot reports the chat as linked (or the link runs out).
//
// Pure: timers, clock, visibility and the window opener are injected, so node tests need no browser.
import { createPoller } from './poller.js'

export const LINK_POLL_MS = 3000

// Opened synchronously inside the click handler (before the request), so browsers do not take it for a
// pop-up. null when the browser refused; the dialog then shows the plain link.
export function openBlankWindow(open = (...args) => window.open(...args)) {
  let win = null
  try { win = open('', '_blank') } catch { win = null }
  if (!win || win.closed) return null
  try { win.opener = null } catch { /* cross-origin handles reject it: harmless */ }
  return win
}

// Sends the blank window to `url`. false when there is no window left to send (blocked, or closed by the user).
export function navigateWindow(win, url) {
  if (!win || win.closed) return false
  try { win.location.href = url } catch { return false }
  return true
}

export function closeWindow(win) {
  try { if (win && !win.closed) win.close() } catch { /* nothing to close */ }
}

// Polls `check()` (→ { linked }) every few seconds while the page is visible. `onLinked(status)` runs once on
// success, `onExpired()` once when `ttlMs` is over; whichever comes first ends the watch.
export function createLinkWatch({
  check, onLinked, onExpired, ttlMs, intervalMs = LINK_POLL_MS,
  setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (id) => clearTimeout(id), ...pollerOptions
}) {
  let done = true
  let expiry = null
  const finish = () => {
    done = true
    poller.stop()
    if (expiry != null) clearTimer(expiry)
    expiry = null
  }
  const poller = createPoller({
    min: intervalMs,
    setTimer,
    clearTimer,
    ...pollerOptions,
    run: async () => {
      const status = await check()
      if (done) return false
      if (status && status.linked) {
        finish()
        onLinked(status)
        return true
      }
      return false
    },
  })
  return {
    start() {
      if (!done) return
      done = false
      expiry = setTimer(() => {
        if (done) return
        finish()
        onExpired()
      }, ttlMs)
      poller.start()
    },
    // Safe to call any time (unmount, "Later", a new link): nothing runs afterwards.
    stop: finish,
    isActive: () => !done,
  }
}
