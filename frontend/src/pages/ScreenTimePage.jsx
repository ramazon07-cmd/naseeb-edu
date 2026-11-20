import { useState, useRef, useCallback, useEffect } from 'react';
import { createLatestRequest } from '../lib/latestRequest';
import { api } from '../api';
import { PageSkeleton, InlineLoadError } from '../components/states';
import { t, tp, tx, formatDurationLocale as formatDuration, formatDateLocale, locale } from '../i18n';
import { CalendarDays, ChevronRight, Clock3, Eye, Gauge, Hourglass, LayoutGrid, Lock, ShieldCheck, Timer } from 'lucide-react';
import { Stat } from '../components/records';
import { Panel, Empty } from '../components/ui';
import { dateText } from '../lib/format';
import { averageSide, averageText } from '../lib/screenTimeAverage';
import { label, initials } from '../lib/labels';
import { isPlatformAdmin } from '../lib/roles';
import { EmptyState, GlassCard, KpiRow, KpiTile, PageHeader, PillTabs, tabId } from '../design/blue/ui';
import '../design/pages/dashboard-blue.css';
import '../design/pages/screentime-blue.css';

export function ScreenTimePage({ user, pageLabel = () => '' }) {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const summaryRequest = useRef(createLatestRequest()).current;
  const load = useCallback(async () => {
    // Switching 7 -> 30 days quickly must not let the slower answer win.
    const isCurrent = summaryRequest.start();
    setLoading(true);
    setError('');
    try {
      const result = await api.screenTimeSummary(days);
      if (isCurrent()) setSummary(result);
    } catch (err) {if (isCurrent()) setError(err.message);} finally {if (isCurrent()) setLoading(false);}
  }, [days, summaryRequest]);
  useEffect(() => {load();return () => summaryRequest.cancel();}, [load, summaryRequest]);

  const student = user.role === 'student';
  if (student) return <StudentScreenTime {...{ days, setDays, summary, loading, error, load, pageLabel }} />;
  if (loading && !summary) return <PageSkeleton />;
  if (error && !summary) return <InlineLoadError message={error} onRetry={load} />;
  const own = summary?.own || { today_seconds: 0, period_seconds: 0, daily: [], pages: [] };
  const dailyByDate = Object.fromEntries(own.daily.map((row) => [row.date, row.seconds]));
  const dates = Array.from({ length: days }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() - (days - offset - 1));
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  });
  const daily = dates.map((date) => ({ date, seconds: dailyByDate[date] || 0 }));
  const maxSeconds = Math.max(1, ...daily.map((row) => row.seconds));
  const isStaff = isPlatformAdmin(user) || ['counselor', 'teacher', 'organization'].includes(user.role);
  return <div className="section-stack screen-time-page">
    <section className="screen-time-intro"><div><span className="eyebrow">{t("ACTIVE LEARNING ONLY")}</span><h2>{t("Time that reflects real work")}</h2><p>{t("Time counts only while this tab is visible and you have interacted in the last minute. Idle and background time are excluded.")}</p></div><label className="period-select"><span>{t("Period")}</span><span className="period-select-control"><CalendarDays size={17} aria-hidden="true" /><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value="7">{t("Last 7 days")}</option><option value="14">{t("Last 14 days")}</option><option value="30">{t("Last 30 days")}</option></select><ChevronRight className="period-select-chevron" size={16} aria-hidden="true" /></span></label></section>
    {error && <div className="alert error">{error}</div>}
    <div className="stat-grid screen-time-stats"><Stat label={t("Today")} value={formatDuration(own.today_seconds)} note={t("Active tab time")} /><Stat label={tx`${days}-day total`} value={formatDuration(own.period_seconds)} note={t("Idle time excluded")} /><Stat label={t("Daily average")} value={formatDuration(own.period_seconds / days)} note={tx`Timezone: ${summary?.timezone || t("Asia/Tashkent")}`} /></div>
    <div className="split-grid wide-left"><Panel title={t("Daily activity")}><div className="time-chart" role="list" aria-label={t("Daily active time chart")}>{daily.map((row) => <div className="time-bar" role="listitem" key={row.date} title={`${dateText(row.date)}: ${formatDuration(row.seconds)}`} aria-label={`${dateText(row.date)}: ${formatDuration(row.seconds)}`}><span><i style={{ height: `${Math.max(row.seconds ? 8 : 2, row.seconds / maxSeconds * 100)}%` }} /></span><small>{new Date(`${row.date}T12:00:00`).toLocaleDateString(locale(), { weekday: 'short' })}</small></div>)}</div></Panel><Panel title={t("Pages")}><div className="page-time-list">{own.pages.slice(0, 8).map((row) => <div key={row.page}><span>{pageLabel(row.page) || label(row.page.replaceAll('_', ' '))}</span><b>{formatDuration(row.seconds)}</b></div>)}{!own.pages.length && <Empty text={t("Your active time will appear after the first 30-second sync.")} />}</div></Panel></div>
    {isStaff && <Panel title={t("Student activity")} action={<span className="privacy-chip"><ShieldCheck size={14} /> {t("Aggregate view")}</span>}><div className="time-team-list">{summary?.team?.map((student) => <article key={student.student}><div><span className="avatar">{initials(student.name)}</span><div><b>{student.name}</b><small>{student.school}</small></div></div><span><small>{t("Today")}</small><b>{formatDuration(student.today_seconds)}</b></span><span><small>{tp('{n} day|{n} days', days, { n: days })}</small><b>{formatDuration(student.period_seconds)}</b></span></article>)}{!summary?.team?.length && <Empty text={t("No permitted student activity is available yet.")} />}</div></Panel>}
    <div className="screen-time-privacy"><ShieldCheck size={18} /><p><b>{t("Privacy by design.")}</b> {t("We store only aggregate seconds by user, day, and app page—never clicks, typed text, or browsing content. Offline totals retry for up to 7 days. Aggregate rows are retained for")} {summary?.retention_days || 365} {t("days.")}</p></div>
  </div>;
}

// The student's page (blue design): the same one summary request as the classic page, laid out like the prototype.
function StudentScreenTime({ days, setDays, summary, loading, error, load, pageLabel }) {
  const [picked, setPicked] = useState(null);
  const own = summary?.own;
  const ready = Boolean(summary);
  const header = <PageHeader title={t('Screen Time')} subtitle={t('How much real study time you spend in the portal.')} />;
  if (!ready && error) return <div className="nb-st">{header}<InlineLoadError message={error} onRetry={load} /></div>;
  const dailyByDate = Object.fromEntries((own?.daily || []).map((row) => [row.date, row.seconds]));
  const today = summary?.today ? new Date(`${summary.today}T12:00:00`) : new Date();
  const rows = ready ? Array.from({ length: days }, (_, offset) => {
    const date = new Date(today);
    date.setDate(date.getDate() - (days - offset - 1));
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    return { key, date, seconds: dailyByDate[key] || 0 };
  }) : [];
  const maximum = Math.max(1, ...rows.map((row) => row.seconds));
  const period = own?.period_seconds || 0;
  const average = period / days;
  const current = rows.find((row) => row.key === picked) || rows[rows.length - 1];
  const dayText = (row, options) => formatDateLocale(`${row.key}T12:00:00`, options);
  const pages = own?.pages || [];
  return <div className="nb-st">
    {header}
    <KpiRow label={t('Summary')} columns={3} className="nb-st-kpis">
      <KpiTile tone={0} icon={Clock3} value={ready ? formatDuration(own.today_seconds) : '—'} label={t('Today')} loading={!ready} />
      <KpiTile tone={1} icon={Gauge} value={ready ? formatDuration(average) : '—'} label={t('Daily average')} loading={!ready} />
      <KpiTile tone={2} icon={Timer} value={ready ? formatDuration(period) : '—'} label={`${t('Total')} · ${tp('{n} day|{n} days', days, { n: days })}`} loading={!ready} />
    </KpiRow>
    {error && <p role="alert" className="nb-dash-save-error">{error}</p>}
    <div className="nb-st-grid">
      <GlassCard className="nb-st-chart" title={t('Active time per day')} icon={Clock3}>
        <PillTabs label={t('Screen Time period')} idPrefix="nb-st-days" value={String(days)} onChange={(key) => { setPicked(null); setDays(Number(key)); }} tabs={[{ key: '7', label: tp('{n} day|{n} days', 7, { n: 7 }) }, { key: '14', label: tp('{n} day|{n} days', 14, { n: 14 }) }, { key: '30', label: tp('{n} day|{n} days', 30, { n: 30 }) }]} />
        <div role="tabpanel" aria-labelledby={tabId('nb-st-days', String(days))} aria-busy={loading}>
          {current && <p className="nb-dash-screen-day" aria-live="polite">{dayText(current, { weekday: 'long', day: 'numeric', month: 'long' })} · {formatDuration(current.seconds)}</p>}
          {!ready ? <p role="status" className="nb-dash-note">{t('Loading…')}</p> : <div className="nb-dash-bars-wrap">
            {period > 0 && <span className={`nb-dash-avg${averageSide(rows, average) === 'start' ? ' is-start' : ''}`} style={{ bottom: `calc(22px + (100% - 22px) * ${(average / maximum).toFixed(4)})` }}><em>{t('avg {value}', { value: averageText(average, formatDuration, t('min')) })}</em></span>}
            <div className={`nb-dash-bars${days === 30 ? ' is-month' : days === 14 ? ' is-fortnight' : ''}`} role="list" aria-label={t('Daily active time chart')}>{rows.map((row, index) => <div key={row.key} role="listitem" className="nb-dash-bar-cell">
              <button type="button" className={`nb-dash-bar${index === rows.length - 1 ? ' is-today' : ''}`} onClick={() => setPicked(row.key)} onFocus={() => setPicked(row.key)} title={`${dayText(row, { weekday: 'short', day: 'numeric', month: 'short' })}: ${formatDuration(row.seconds)}`} aria-label={`${dayText(row, { weekday: 'long', day: 'numeric', month: 'long' })}: ${formatDuration(row.seconds)}`}>
                <span><i style={{ height: `${Math.max(row.seconds ? 6 : 0, row.seconds / maximum * 100)}%` }} /></span>
                <small>{days === 7 ? dayText(row, { weekday: 'short' }) : index % (days === 14 ? 2 : 7) === 0 || index === days - 1 ? row.date.getDate() : ''}</small>
              </button>
            </div>)}</div>
          </div>}
          {ready && !period && <small className="nb-dash-note">{t('No activity in this period.')}</small>}
          <p className="nb-st-hint">{t('Minutes per day. Tap a bar to see the day.')}</p>
        </div>
      </GlassCard>
      <GlassCard className="nb-st-pages" title={t('Time per page')} icon={LayoutGrid}>
        {ready && pages.length > 0 ? <ul className="nb-st-pagelist">{pages.slice(0, 8).map((row) => <li key={row.page}><span>{pageLabel(row.page) || label(row.page.replaceAll('_', ' '))}</span><b>{formatDuration(row.seconds)}</b></li>)}</ul>
          : ready ? <EmptyState icon={Hourglass} title={t('No time per page yet')} text={t('It fills in as you use Tasks, Essay Lab, Programs and the other pages.')} /> : <p role="status" className="nb-dash-note">{t('Loading…')}</p>}
      </GlassCard>
    </div>
    <GlassCard className="nb-st-privacy" title={t('Your privacy')} icon={ShieldCheck}>
      <ul className="nb-st-priv">
        <li><span aria-hidden="true"><Eye size={18} /></span><div><b>{t('Only active time counts')}</b><small>{t('The tab is open on screen and you used it in the last minute.')}</small></div></li>
        <li><span aria-hidden="true"><Lock size={18} /></span><div><b>{t('Only totals are stored')}</b><small>{t('Never your clicks or what you type.')}</small></div></li>
      </ul>
    </GlassCard>
  </div>;
}
