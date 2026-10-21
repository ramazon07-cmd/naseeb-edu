import { useEffect, useState } from 'react';
import { ChevronRight, Clock3 } from 'lucide-react';
import { api } from '../api';
import { t, formatClockDurationLocale } from '../i18n';
import { SCREEN_TIME_REFRESH_MS } from '../screenTimeQueue';
import { createPoller } from '../lib/poller';

export function ScreenTimeShortcut({ setPage, userId }) {
  const [seconds, setSeconds] = useState(null);
  useEffect(() => {
    let active = true;
    const loop = createPoller({
      min: SCREEN_TIME_REFRESH_MS,
      failureCap: SCREEN_TIME_REFRESH_MS * 5,
      run: () => api.screenTimeSummary(7).then((result) => { if (active) setSeconds(result.own?.today_seconds ?? 0); return true; }, () => { if (active) setSeconds(null); return null; }),
    });
    loop.start({ immediate: true });
    return () => { active = false; loop.stop(); };
  }, [userId]);
  return <button className="dashboard-time" onClick={() => setPage('screen_time')} title={t('Screen Time')}><Clock3 size={16} /><span>{t('Screen Time')}</span><b>{seconds === null ? '—' : formatClockDurationLocale(seconds)}</b><ChevronRight size={14} /></button>;
}

