import { useState, useRef, useCallback, useEffect } from 'react';
import { createLatestRequest } from '../lib/latestRequest';
import { api } from '../api';
import { PageSkeleton, InlineLoadError } from '../components/states';
import { t, tp, formatDurationLocale as formatDuration, tx, locale } from '../i18n';
import { CalendarDays, ChevronRight, ShieldCheck } from 'lucide-react';
import { Stat } from '../components/records';
import { Panel, Empty } from '../components/ui';
import { dateText } from '../lib/format';
import { label, initials } from '../lib/labels';
import { isPlatformAdmin } from '../lib/roles';

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
