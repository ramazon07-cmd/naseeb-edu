import { createContext, useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { createPoller } from '../lib/poller';
import { nextPollDelay } from '../lib/pollDelay';
import { BELL_POLL, NOTIFICATIONS_CHANGED, summaryChanged } from '../lib/notifications';

// The bell's latest summary and whether its request failed, for pages inside the student shell
// (they read it instead of asking again).
export const BellSummaryContext = createContext(undefined);

const nextBellDelay = (delay, changed) => nextPollDelay(delay, changed, BELL_POLL);

// Unread counts behind the bell, polled from the server while the tab is
// visible (see lib/poller.js). `refresh()` asks for a fresh count now.
export function useNotificationBell(enabled) {
  const [summary, setSummary] = useState(null);
  // True while the last summary request failed (the poller retries on its own back-off).
  const [failed, setFailed] = useState(false);
  const loopRef = useRef(null);

  useEffect(() => {
    if (!enabled) {
      setSummary(null);
      return undefined;
    }
    let active = true;
    let last = null;
    const loop = createPoller({
      min: BELL_POLL.min,
      max: BELL_POLL.max,
      nextDelay: nextBellDelay,
      run: async () => {
        let next;
        try { next = await api.notificationSummary(); } catch (error) { if (active) setFailed(true); throw error; }
        if (!active) return false;
        setFailed(false);
        const changed = summaryChanged(last, next);
        last = next;
        if (changed) setSummary(next);
        return changed;
      },
    });
    loopRef.current = loop;
    loop.start({ immediate: true });
    const onChanged = () => loop.poke();
    window.addEventListener(NOTIFICATIONS_CHANGED, onChanged);
    return () => {
      active = false;
      loop.stop();
      window.removeEventListener(NOTIFICATIONS_CHANGED, onChanged);
      if (loopRef.current === loop) loopRef.current = null;
    };
  }, [enabled]);

  const refresh = useCallback(() => loopRef.current?.poke(), []);
  return { summary, failed, refresh };
}
