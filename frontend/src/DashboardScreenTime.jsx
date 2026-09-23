import { useEffect, useState } from 'react';
import { api } from './api';
import { t, locale } from './i18n';

const duration = (seconds) => `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
export default function DashboardScreenTime({ userId }) {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    let busy = false;
    setSummary(null); setError('');
    const load = async () => {
      if (busy || document.hidden) return;
      busy = true;
      try { const result = await api.screenTimeSummary(days); if (active) { setSummary(result); setError(''); } }
      catch (err) { if (active) setError(err.message); }
      finally { busy = false; }
    };
    load();
    const timer = setInterval(load, 60000);
    document.addEventListener('visibilitychange', load);
    return () => { active = false; clearInterval(timer); document.removeEventListener('visibilitychange', load); };
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
    {error ? <div role="alert" className="screen-time-error">{error}<button onClick={() => setRetry(value => value+1)}>{t('Retry')}</button></div> : !summary ? <p role="status" className="dashboard-empty">{t('Loading…')}</p> : <><div className="dashboard-time-bars" aria-label={t('Daily active time chart')}>{rows.map((row,index) => <div key={row.key} className="dashboard-time-bar" tabIndex={0} title={`${row.key}: ${duration(row.seconds)}`} aria-label={`${row.key}: ${duration(row.seconds)}`}><span><i style={{height:`${row.seconds / maximum * 100}%`}} /></span><small>{days === 7 ? row.date.toLocaleDateString(locale(), {weekday:'short'}) : index % 7 === 0 || index === days-1 ? row.date.getDate() : ''}</small></div>)}</div>{!summary.own?.period_seconds && <small className="screen-time-empty">{t('No activity in this period.')}</small>}</>}
  </div>;
}
