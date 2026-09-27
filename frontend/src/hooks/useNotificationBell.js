import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { createPoller } from '../lib/poller';
import { nextPollDelay } from '../lib/pollDelay';
import { BELL_POLL, NOTIFICATIONS_CHANGED, summaryChanged } from '../lib/notifications';

const nextBellDelay = (delay, changed) => nextPollDelay(delay, changed, BELL_POLL);

// Unread counts behind the bell, polled from the server while the tab is
// visible (see lib/poller.js). `refresh()` asks for a fresh count now.
export function useNotificationBell(enabled) {
  const [summary, setSummary] = useState(null);
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
        const next = await api.notificationSummary();
        if (!active) return false;
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
  return { summary, refresh };
}
