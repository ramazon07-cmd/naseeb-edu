import { useEffect, useState } from 'react';
import { api } from './api';
import { t, formatClockDurationLocale, formatDateLocale, locale } from './i18n';
import { createPoller } from './lib/poller';
import { SCREEN_TIME_REFRESH_MS } from './screenTimeQueue';

const duration = (seconds) => formatClockDurationLocale(seconds);
export default function DashboardScreenTime({ userId }) {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setSummary(null); setError('');
    // Refreshes every minute while the tab is visible; nothing runs in a hidden tab.
    const loop = createPoller({
      min: SCREEN_TIME_REFRESH_MS,
      failureCap: SCREEN_TIME_REFRESH_MS * 5,
      run: async () => {
        try { const result = await api.screenTimeSummary(days); if (active) { setSummary(result); setError(''); } return true; }
        catch (err) { if (active) setError(err.message); return null; }
      },
    });
    loop.start({ immediate: true });
    return () => { active = false; loop.stop(); };
  }, [days, userId, retry]);
  const rows = [];
  if (summary) {
    const totals = new Map((summary.own?.daily || []).map(row => [row.date, row.seconds]));
    const today = new Date(`${summary.today}T12:00:00`);
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date(today); date.setDate(date.getDate() - i);
      const key = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
      rows.push({key, date, seconds: totals.get(key) || 0});
    }
  }
  const maximum = Math.max(1, ...rows.map(row => row.seconds));
  return <div className="dashboard-screen-time">
    <div className="screen-time-toolbar"><strong>{summary ? duration(summary.own?.period_seconds || 0) : '—'}</strong><select aria-label={t('Screen Time period')} value={days} onChange={event => setDays(Number(event.target.value))}><option value={7}>{t('Last 7 days')}</option><option value={30}>{t('Last 30 days')}</option></select></div>
    {error ? <div role="alert" className="screen-time-error">{error}<button onClick={() => setRetry(value => value+1)}>{t('Retry')}</button></div> : !summary ? <p role="status" className="dashboard-empty">{t('Loading…')}</p> : <><div className="dashboard-time-bars" role="list" aria-label={t('Daily active time chart')}>{rows.map((row,index) => <div key={row.key} role="listitem" className="dashboard-time-bar" tabIndex={0} title={`${formatDateLocale(`${row.key}T12:00:00`, { weekday: 'short', day: 'numeric', month: 'short' })}: ${duration(row.seconds)}`} aria-label={`${formatDateLocale(`${row.key}T12:00:00`, { weekday: 'long', day: 'numeric', month: 'long' })}: ${duration(row.seconds)}`}><span><i style={{height:`${row.seconds / maximum * 100}%`}} /></span><small>{days === 7 ? row.date.toLocaleDateString(locale(), {weekday:'short'}) : index % 7 === 0 || index === days-1 ? row.date.getDate() : ''}</small></div>)}</div>{!summary.own?.period_seconds && <small className="screen-time-empty">{t('No activity in this period.')}</small>}</>}
  </div>;
}
