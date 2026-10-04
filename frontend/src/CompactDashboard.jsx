import { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarClock, ChevronRight, Clock3, Fingerprint, Globe2, GraduationCap, MessageCircle, School, SlidersHorizontal, Target, Telescope, UsersRound, ArrowUpRight, Star, Map, Plus } from 'lucide-react';
import { api } from './api';
import { t, tp, tx, formatClockDurationLocale, formatPercentLocale, formatDateLocale } from './i18n';
import { dateTimeText, dayMonthText } from './lib/format';
import { daysUntil } from './lib/college';
import { nextPriorities, studentProgress } from './lib/metrics';
import { upcomingMeetings } from './lib/meetings';
import { dashboardColumns, normalizeDashboardPreferences } from './dashboardPreferences';
import './dashboard.css';
import DashboardScreenTime from './DashboardScreenTime';
import { SCREEN_TIME_REFRESH_MS } from './screenTimeQueue';
import { createPoller } from './lib/poller';
import { listText } from './lib/profileSections';
import DashboardCustomizer from './DashboardCustomizer';
import { cachedDashboardLayout, loadAccountDashboardLayout, saveAccountDashboardLayout } from './dashboardLayout';

const widgetMeta = {
  screen_time: ['Screen Time', Clock3],
  journey: ['Study goal', Target], tasks: ['Next priorities', Target],
  meetings: ['Meetings', CalendarClock], applications: ['Applications', GraduationCap],
  discovery: ['Student discovery tools', Telescope], team: ['My Naseeb team', UsersRound], roadmap: ['Roadmap', Map],
  programs: ['Programs', Globe2],
};

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

const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// Counts up to `value` once it is known, on the same curve the tiles rise on.
function useCountUp(value, duration = 900) {
  const target = Number(value) || 0;
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? target : 0));
  const from = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion()) { setShown(target); return undefined; }
    const start = performance.now();
    const origin = from.current;
    let frame;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - p) ** 4;
      setShown(Math.round(origin + (target - origin) * eased));
      if (p < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return shown;
}

// A leaf, so only the number re-renders on every animation frame.
function CountUp({ value, format = String }) {
  return format(useCountUp(value));
}

// The catalog is large, so this tile fetches it itself instead of holding up the dashboard.
function ProgramsTile({ programs, status, load, retry, setPage, open }) {
  useEffect(() => { load(); }, [load]);
  // Programs still taking applications, nearest deadline first; most of the
  // catalog only has a yearly text deadline, so those count toward the total only.
  const openPrograms = useMemo(() => programs
    .map((item) => [item, daysUntil(item.deadline)])
    .filter(([, days]) => days != null && days >= 0)
    .sort(([, a], [, b]) => a - b)
    .map(([item]) => item), [programs]);
  if (status?.status === 'error' && !status.loaded) return <div role="alert" className="screen-time-error">{status.error}<button onClick={retry}>{t('Retry')}</button></div>;
  if (!status?.loaded) return <p role="status" className="dashboard-empty">{t('Loading…')}</p>;
  return <><div className="dashboard-number dashboard-programs-number"><CountUp value={openPrograms.length || programs.length} /><small>{openPrograms.length ? t('Open for applications') : t('Programs in the catalog')}</small></div><div className="dashboard-card-list dashboard-program-list">{openPrograms.slice(0, 1).map((item) => <button key={item.id} onClick={() => setPage('programs')}><span><b>{item.title}</b><small>{item.provider} · {dayMonthText(item.deadline)}</small></span><ChevronRight size={16} /></button>)}</div>{open('programs', 'Explore programs')}</>;
}

// The board's content width, which decides (like the CSS container query) how many tiles fit across.
function useBoardWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const board = ref.current;
    if (!board || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(board);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

// The light under the pointer, as tile-local coordinates; CSS draws it only on fine pointers.
function trackSpotlight(event) {
  const tile = event.target.closest?.('.dashboard-tile');
  if (!tile) return;
  const rect = tile.getBoundingClientRect();
  tile.style.setProperty('--mx', `${event.clientX - rect.left}px`);
  tile.style.setProperty('--my', `${event.clientY - rect.top}px`);
}

export default function CompactDashboard({ user, student, data, setPage, onDirect, Modal, programUsage, programsStatus, loadPrograms, retryPrograms }) {
  // This browser's copy first, then the account's layout (see dashboardLayout.js).
  const [preferences, setPreferences] = useState(() => normalizeDashboardPreferences(cachedDashboardLayout(user.id)));
  useEffect(() => {
    let active = true;
    loadAccountDashboardLayout(user.id).then((layout) => { if (active) setPreferences(layout); });
    return () => { active = false; };
  }, [user.id]);
  const [usageOpen, setUsageOpen] = useState(false);
  const [customizing, setCustomizing] = useState(false);
  const [draft, setDraft] = useState(preferences);
  const [saveError, setSaveError] = useState(false);
  const pending = nextPriorities(data.tasks);
  const numbers = studentProgress(student);
  const stars = numbers.missionsApproved;
  const meetings = upcomingMeetings(data.bookings);
  const progress = numbers.roadmapPercent;
  const openTasks = () => setPage('roadmap', { tab: 'tasks' });
  const editGoal = () => setPage('student_center', { edit: 'goal' });
  const name = user.first_name || user.username;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const [boardRef, boardWidth] = useBoardWidth();
  const columns = dashboardColumns(preferences, boardWidth);
  const missionSteps = numbers.missionsTotal > 0 && numbers.missionsTotal <= 12 ? Array.from({ length: numbers.missionsTotal }, (_, index) => index < numbers.missionsApproved) : null;
  function save() {
    const layout = draft;
    setPreferences(layout);
    setCustomizing(false);
    setSaveError(false);
    saveAccountDashboardLayout(user.id, layout).then(({ synced }) => setSaveError(!synced));
  }
  const open = (page, text, params) => <button className="dashboard-link" onClick={() => setPage(page, params)}>{t(text)}<ChevronRight size={15} /></button>;
  const empty = (text) => <p className="dashboard-empty">{t(text)}</p>;
  const content = {
    screen_time: <DashboardScreenTime userId={user.id} />,
    journey: <><div className="dashboard-goal-body"><button className="dashboard-goal-symbol" onClick={editGoal} aria-label={t('Edit study goal')}><span className="dashboard-goal-orbit" aria-hidden="true" />{student?.target_major ? <GraduationCap size={32} strokeWidth={1.5} /> : <Plus size={30} />}</button><div><h4>{student?.target_major || t('Set your study goal')}</h4><p>{listText(student?.target_countries) || t('Choose your study interests and destination.')}</p><span className="dashboard-goal-pill"><Star size={13} />{tx`Level ${student?.level || 1}`}<span>·</span>{tp('{n} star|{n} stars', stars, { n: stars })}</span></div></div><div className="dashboard-goal-footer">{open('student_center', 'Edit study goal', { edit: 'goal' })}<button className="dashboard-link" onClick={() => setUsageOpen(true)}>{t('Program usage')}<ArrowUpRight size={14} /></button></div></>,
    roadmap: <><div className="dashboard-roadmap-value"><strong><CountUp value={progress} format={formatPercentLocale} /></strong></div>{missionSteps ? <div className="dashboard-mission-steps" role="progressbar" aria-label={t('Roadmap progress')} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>{missionSteps.map((done, index) => <i key={index} className={done ? 'done' : index === numbers.missionsApproved ? 'current' : ''} style={{ '--s': index }} />)}</div> : <div className="dashboard-progress-track" role="progressbar" aria-label={t('Roadmap progress')} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ '--fill': progress / 100 }} /></div>}{numbers.missionsTotal > 0 ? <div className="dashboard-application-stats dashboard-roadmap-stats"><span><b>{numbers.missionsApproved}/{numbers.missionsTotal}</b>{t('Missions approved')}</span>{numbers.levelTotal > 0 && <span><b>{numbers.levelApproved}/{numbers.levelTotal}</b>{t('This level')}</span>}</div> : <p className="dashboard-roadmap-caption">{t('No roadmap missions assigned yet.')}</p>}{open('roadmap', 'Open roadmap', { tab: 'path' })}</>,
    tasks: <><div className="dashboard-card-list">{pending.slice(0, 3).map((task, index) => <button key={task.id} onClick={openTasks}><i className="dashboard-task-index">{String(index + 1).padStart(2, '0')}</i><span><b>{task.title}</b><small>{task.due_date ? formatDateLocale(task.due_date) : t('No deadline')}</small></span><ChevronRight size={16} /></button>)}{!pending.length && empty('All tasks are complete.')}</div><div className="dashboard-card-foot"><span>{tp('{n} open task|{n} open tasks', pending.length, { n: pending.length })}</span>{open('roadmap', 'View all', { tab: 'tasks' })}</div></>,
    meetings: <><div className="dashboard-card-list">{meetings.slice(0, 2).map((meeting) => <button key={meeting.id} onClick={() => setPage('bookings')}><CalendarClock size={20} /><span><b>{meeting.topic || t('Meeting')}</b><small>{dateTimeText(meeting.starts_at)}</small></span><ChevronRight size={16} /></button>)}{!meetings.length && <div className="dashboard-meeting-empty"><CalendarClock size={28} strokeWidth={1.3} />{empty('No upcoming meetings.')}<small>{t('Make time for your next step.')}</small></div>}</div>{open('bookings', meetings.length ? 'View all' : 'Request a meeting')}</>,
    applications: <><div className="dashboard-number"><CountUp value={numbers.applicationsTotal} /><small>{t('Universities on your list')}</small></div><div className="dashboard-application-stats"><span><b>{numbers.applicationsSubmitted}</b>{t('Submitted')}</span><span><b>{data.essays.length}</b>{t('Essays')}</span><span><b>{numbers.applicationsAccepted}</b>{t('Accepted')}</span><span><b>{numbers.achievementsTotal}</b>{t('Achievements')}</span></div>{open('applications', 'View applications')}</>,
    discovery: <div className="dashboard-discovery-editorial"><button onClick={() => setPage('find_personality')}><span className="discovery-tool-icon"><Fingerprint size={22} strokeWidth={1.75} /></span><span className="discovery-tool-copy"><b>{t('Profile Assessment')}</b><p>{t('Discover your strengths and study interests.')}</p></span><span className="discovery-tool-arrow"><ArrowUpRight size={15} /></span></button><button onClick={() => setPage('college_search')}><span className="discovery-tool-icon"><School size={22} strokeWidth={1.75} /></span><span className="discovery-tool-copy"><b>{t('College Search')}</b><p>{t('Compare universities with your goals.')}</p></span><span className="discovery-tool-arrow"><ArrowUpRight size={15} /></span></button></div>,
    programs: <ProgramsTile programs={data.opportunityPrograms} status={programsStatus} load={loadPrograms} retry={retryPrograms} setPage={setPage} open={open} />,
    team: <><div className="dashboard-card-list">{data.team.slice(0, 2).map((member) => <button key={`${member.kind}-${member.id}`} onClick={() => onDirect(member.id)}><span className="dashboard-initial">{member.name?.charAt(0)}</span><span><b>{member.name}</b><small>{t(member.role)}</small></span><MessageCircle size={16} /></button>)}{!data.team.length && empty('No team members have been assigned yet.')}</div>{open('messages', 'Open messages')}</>,
  };
  return <section className="compact-dashboard reference-dashboard">
    <header className="dashboard-heading"><div className="dashboard-greeting"><h2><span>{t(greeting)},</span> {name}</h2></div><div className="dashboard-heading-actions"><button className="button quiet small" onClick={() => { setDraft(preferences); setCustomizing(true); }}><SlidersHorizontal size={16} />{t('Customize')}</button></div></header>
    {saveError && <p role="status">{t('Layout saved on this device. It will be saved to your account when you are back online.')}</p>}
    <div ref={boardRef} onPointerMove={trackSpotlight} className={`dashboard-board dashboard-board-columns ${columns.some((item) => item.column === 'rail') ? 'has-rail' : ''} ${columns.some((item) => item.column === 'main') ? 'has-main' : ''} ${columns[0].across === 1 ? 'has-stacked-main' : ''} ${columns.some((item) => item.fewRows) ? 'has-few-rows' : ''}`.trim()}>{columns.map(({ column, ids, rows, across, lastSpan, wideLast, teamFooter }) => <div key={column} className={`dashboard-column dashboard-column-${column} ${column === 'main' && across === 1 ? 'is-stacked' : ''} ${across === 3 ? 'is-three' : ''} ${wideLast ? 'has-wide-last' : ''} ${teamFooter ? 'has-team-footer' : ''}`.trim()} style={{ '--widget-rows': rows, '--last-span': lastSpan }}>{ids.map((id, index) => { const [title, Icon] = widgetMeta[id]; return <article key={id} className={`dashboard-tile dashboard-tile-${id} dashboard-position-${column === 'rail' ? index + 2 : index}`} style={{ '--i': column === 'rail' ? index * 2 + 1 : index }}><header><Icon size={18} /><h3>{t(title)}</h3></header>{content[id]}</article>; })}</div>)}</div>
    {usageOpen && <Modal title={t('Program usage')} onClose={() => setUsageOpen(false)}>{data.programServices.length ? programUsage : <p className="dashboard-empty">{t('No program services have been assigned yet.')}</p>}</Modal>}
    {customizing && <DashboardCustomizer draft={draft} setDraft={setDraft} metadata={widgetMeta} Modal={Modal} onClose={() => setCustomizing(false)} onSave={save} />}
  </section>;
}
