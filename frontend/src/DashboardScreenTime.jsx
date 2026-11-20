import { useEffect, useState } from 'react';
import { api } from './api';
import { t, formatClockDurationLocale, formatDateLocale } from './i18n';
import { createPoller } from './lib/poller';
import { SCREEN_TIME_REFRESH_MS } from './screenTimeQueue';
import { PillTabs, tabId } from './design/blue/ui';
import { averageSide, averageText } from './lib/screenTimeAverage';

const duration = (seconds) => formatClockDurationLocale(seconds);
export default function DashboardScreenTime({ userId }) {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [picked, setPicked] = useState(null);
  useEffect(() => {
    let active = true;
    setSummary(null); setError(''); setPicked(null);
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
  const period = summary?.own?.period_seconds || 0;
  const average = days ? period / days : 0;
  const averageLabel = averageText(average, duration, t('min'));
  const avgSide = averageSide(rows, average) === 'start' ? ' is-start' : '';
  const periodLabel = days === 7 ? t('Last 7 days') : t('Last 30 days');
  return <div className="nb-dash-screen-time">
    <PillTabs label={t('Screen Time period')} idPrefix="nb-dash-screen" value={String(days)} onChange={(key) => setDays(Number(key))} tabs={[{ key: '7', label: t('Last 7 days') }, { key: '30', label: t('Last 30 days') }]} />
    <div role="tabpanel" aria-labelledby={tabId('nb-dash-screen', String(days))}>
      <div className="nb-dash-screen-total"><strong>{summary ? duration(period) : '—'}</strong><span>{periodLabel}</span></div>
      {summary && rows.length > 0 && (() => { const row = rows.find((item) => item.key === picked) || rows[rows.length - 1]; return <p className="nb-dash-screen-day" aria-live="polite">{formatDateLocale(`${row.key}T12:00:00`, { weekday: 'short', day: 'numeric', month: 'short' })} · {duration(row.seconds)}</p>; })()}
      {error ? <div role="alert" className="nb-dash-error">{error}<button type="button" onClick={() => setRetry(value => value+1)}>{t('Retry')}</button></div> : !summary ? <p role="status" className="nb-dash-note">{t('Loading…')}</p> : <>
        <div className="nb-dash-bars-wrap">
          {period > 0 && <span className={`nb-dash-avg${avgSide}`} style={{ bottom: `calc(22px + (100% - 22px) * ${(average / maximum).toFixed(4)})` }}><em>{t('avg {value}', { value: averageLabel })}</em></span>}
          <div className={`nb-dash-bars${days === 30 ? ' is-month' : ''}`} role="list" aria-label={t('Daily active time chart')}>{rows.map((row,index) => <div key={row.key} role="listitem" className="nb-dash-bar-cell"><button type="button" className={`nb-dash-bar${index === rows.length - 1 ? ' is-today' : ''}`} onClick={() => setPicked(row.key)} onFocus={() => setPicked(row.key)} title={`${formatDateLocale(`${row.key}T12:00:00`, { weekday: 'short', day: 'numeric', month: 'short' })}: ${duration(row.seconds)}`} aria-label={`${formatDateLocale(`${row.key}T12:00:00`, { weekday: 'long', day: 'numeric', month: 'long' })}: ${duration(row.seconds)}`}><span><i style={{height:`${Math.max(row.seconds ? 6 : 0, row.seconds / maximum * 100)}%`}} /></span><small>{days === 7 ? formatDateLocale(row.date, { weekday: 'short' }) : index % 7 === 0 || index === days-1 ? row.date.getDate() : ''}</small></button></div>)}</div>
        </div>
        {!period && <small className="nb-dash-note">{t('No activity in this period.')}</small>}
      </>}
    </div>
  </div>;
}
