// A polling loop that only runs while the page is visible.
//
//  - Hidden tab: no requests and no timers; the loop is paused.
//  - Visible again: one immediate refresh, then the normal cadence. If the
//    last successful run started under `revisitMin` ago (quick tab flips),
//    skip the refresh and just resume the cadence.
//  - `run()` resolves to true (something changed), false (nothing new) or
//    throws / resolves to null (failed). Success delays follow `nextDelay`;
//    failures back off exponentially with full jitter, starting from `min`.
//  - Only one run at a time; `poke()` (focus, a send) asks for a run now.
//
// Pure: timers, clock, visibility and randomness are injected for node tests.
import { backoffDelay } from './backoff.js'

export function createPoller({
  run,
  min,
  max = min,
  nextDelay = () => min,
  failureCap = max,
  revisitMin = Math.round(min / 4),
  now = () => Date.now(),
  random = Math.random,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  isHidden = () => typeof document !== 'undefined' && document.hidden,
  onVisibilityChange = (listener) => {
    if (typeof document === 'undefined') return () => {}
    document.addEventListener('visibilitychange', listener)
    return () => document.removeEventListener('visibilitychange', listener)
  },
}) {
  let delay = min
  let failures = 0
  let timer = null
  let busy = false
  let again = false
  let stopped = true
  let lastOkAt = null
  let unsubscribe = null

  const cancel = () => { if (timer != null) clearTimer(timer); timer = null }

  function schedule(ms) {
    cancel()
    if (stopped || isHidden()) return
    timer = setTimer(() => { timer = null; tick() }, ms)
  }

  async function tick() {
    if (stopped || isHidden()) return
    if (busy) { again = true; return }
    busy = true
    cancel()
    let result = null
    const startedAt = now()
    try {
      result = await run()
    } catch {
      result = null
    } finally {
      busy = false
    }
    if (stopped) return
    if (result === null || result === undefined) {
      // Never faster than `min / 8`, so a flapping server isn't hammered.
      schedule(Math.max(Math.round(min / 8), backoffDelay(failures, { base: min, cap: failureCap }, random)))
      failures += 1
    } else {
      failures = 0
      lastOkAt = startedAt
      delay = nextDelay(delay, Boolean(result))
      schedule(again ? 0 : delay)
    }
    again = false
  }

  function onVisibility() {
    if (isHidden()) { cancel(); return }
    delay = min
    // An in-flight run reschedules itself when it settles.
    if (busy) return
    const since = lastOkAt == null ? Infinity : now() - lastOkAt
    if (since < revisitMin) schedule(Math.max(0, min - since))
    else tick()
  }

  return {
    // `immediate`: run now; otherwise the first run is after `min`.
    start({ immediate = false } = {}) {
      if (!stopped) return
      stopped = false
      unsubscribe = onVisibilityChange(onVisibility)
      if (immediate) tick()
      else schedule(delay)
    },
    stop() {
      stopped = true
      cancel()
      if (unsubscribe) unsubscribe()
      unsubscribe = null
    },
    poke() {
      delay = min
      failures = 0
      tick()
    },
    // Back to the fastest cadence without an extra request now.
    reset() {
      delay = min
      failures = 0
      if (timer != null) schedule(delay)
    },
    getState: () => ({ delay, failures, scheduled: timer != null, busy, stopped }),
  }
}
