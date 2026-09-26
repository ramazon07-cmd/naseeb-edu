import { userStorageKey, USER_STORAGE } from '../userStorage';
import { useRef, useMemo, useEffect } from 'react';
import { createScreenTimeSync } from '../screenTimeQueue';
import { api } from '../api';
import { localDateKey } from '../lib/format';

// Lets sign-out upload the signed-in user's queued seconds before the tokens go.
export let flushActiveScreenTime = null;

export function ScreenTimeTracker({ page, userId }) {
  const storageKey = userStorageKey(USER_STORAGE.screenTime, userId);
  const activeSeconds = useRef(0);
  const lastInteraction = useRef(Date.now());
  const sync = useMemo(() => createScreenTimeSync({
    load: () => {try {return JSON.parse(localStorage.getItem(storageKey) || '[]');} catch {return [];}},
    // Storage can be full or blocked (private mode); the queue then lives in memory only.
    save: (entries) => {try {if (entries.length) localStorage.setItem(storageKey, JSON.stringify(entries));else localStorage.removeItem(storageKey);} catch {/* storage unavailable */}},
    send: (batch) => api.trackScreenTime(batch),
    today: localDateKey,
    isOnline: () => navigator.onLine
  }), [storageKey]);

  useEffect(() => {
    const markInteraction = () => {lastInteraction.current = Date.now();};
    const events = ['pointerdown', 'keydown', 'scroll', 'touchstart'];
    events.forEach((eventName) => window.addEventListener(eventName, markInteraction, { passive: true }));

    // Seconds recorded while an upload is in flight are merged into the latest
    // queue (createScreenTimeSync), so overlapping flushes cannot lose them.
    const persistAndSend = async (force = false) => {
      // After sign-out nothing may be written back under the old account.
      if (!api.hasSession()) return;
      const seconds = activeSeconds.current;
      activeSeconds.current = 0;
      sync.record(page, seconds);
      await sync.flush({ force: force === true });
    };
    const sendNow = () => persistAndSend(true);
    const tick = window.setInterval(() => {if (document.visibilityState === 'visible' && Date.now() - lastInteraction.current < 60_000) activeSeconds.current += 1;
      }, 1_000);
    const flush = window.setInterval(persistAndSend, 30_000);
    const onVisibility = () => {if (document.visibilityState === 'hidden') persistAndSend();};
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('online', sendNow);
    persistAndSend();
    flushActiveScreenTime = sendNow;
    return () => {
      if (flushActiveScreenTime === sendNow) flushActiveScreenTime = null;
      window.clearInterval(tick);
      window.clearInterval(flush);
      events.forEach((eventName) => window.removeEventListener(eventName, markInteraction));
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('online', sendNow);
      persistAndSend();
    };
  }, [page, sync]);
  return null;
}
