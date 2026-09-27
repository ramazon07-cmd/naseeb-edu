import { useEffect, useState } from 'react';
import { CalendarClock, ChevronRight, Clock3, Fingerprint, GraduationCap, MessageCircle, SlidersHorizontal, Target, UsersRound, ArrowUpRight, Star, Map, Plus } from 'lucide-react';
import { api } from './api';
import { t, tp, tx, formatClockDurationLocale, formatPercentLocale, formatDateLocale } from './i18n';
import { dateTimeText } from './lib/format';
import { nextPriorities, studentProgress } from './lib/metrics';
import { upcomingMeetings } from './lib/meetings';
import { normalizeDashboardPreferences } from './dashboardPreferences';
import './dashboard.css';
import DashboardScreenTime from './DashboardScreenTime';
import { SCREEN_TIME_REFRESH_MS } from './screenTimeQueue';
import { createPoller } from './lib/poller';
import { listText } from './lib/profileSections';
import DashboardCustomizer from './DashboardCustomizer';

const widgetMeta = {
  screen_time: ['Screen Time', Clock3],
  journey: ['Study goal', Target], tasks: ['Next priorities', Target],
  meetings: ['Meetings', CalendarClock], applications: ['Applications', GraduationCap],
  discovery: ['Student discovery tools', Fingerprint], team: ['My Naseeb team', UsersRound], roadmap: ['Roadmap', Map],
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

export default function CompactDashboard({ user, student, data, setPage, onDirect, Modal, programUsage }) {
  const storageKey = `naseeb-dashboard-v1:${user.id}`;
  const [preferences, setPreferences] = useState(() => {
    try { return normalizeDashboardPreferences(JSON.parse(localStorage.getItem(storageKey))); } catch { return normalizeDashboardPreferences(); }
  });
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
  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(draft)); setSaveError(false); } catch { setSaveError(true); }
    setPreferences(draft);
    setCustomizing(false);
  }
  const open = (page, text, params) => <button className="dashboard-link" onClick={() => setPage(page, params)}>{t(text)}<ChevronRight size={15} /></button>;
  const empty = (text) => <p className="dashboard-empty">{t(text)}</p>;
  const content = {
    screen_time: <DashboardScreenTime userId={user.id} />,
    journey: <><div className="dashboard-goal-body"><button className="dashboard-goal-symbol" onClick={editGoal} aria-label={t('Edit study goal')}>{student?.target_major ? <GraduationCap size={32} strokeWidth={1.5} /> : <Plus size={30} />}</button><div><h4>{student?.target_major || t('Set your study goal')}</h4><p>{listText(student?.target_countries) || t('Choose your study interests and destination.')}</p><span className="dashboard-goal-pill"><Star size={13} />{tx`Level ${student?.level || 1}`}<span>·</span>{tp('{n} star|{n} stars', stars, { n: stars })}</span></div></div><div className="dashboard-goal-footer">{open('student_center', 'Edit study goal', { edit: 'goal' })}<button className="dashboard-link" onClick={() => setUsageOpen(true)}>{t('Program usage')}<ArrowUpRight size={14} /></button></div></>,
    roadmap: <><div className="dashboard-roadmap-value"><strong>{formatPercentLocale(progress)}</strong><span>{t('Roadmap progress')}</span>{open('roadmap', 'Open roadmap', { tab: 'path' })}</div><div className="dashboard-progress-track" role="progressbar" aria-label={t('Roadmap progress')} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{width: `${progress}%`}} /></div><p className="dashboard-roadmap-caption">{numbers.missionsTotal > 0 ? <><span>{tp('Roadmap: {done} of {n} mission approved|Roadmap: {done} of {n} missions approved', numbers.missionsTotal, { done: numbers.missionsApproved, n: numbers.missionsTotal })}</span>{numbers.levelTotal > 0 && <span>{t('This level: {done} of {n}', { done: numbers.levelApproved, n: numbers.levelTotal })}</span>}</> : t('No roadmap missions assigned yet.')}</p></>,
    tasks: <><div className="dashboard-card-list">{pending.slice(0, 3).map((task, index) => <button key={task.id} onClick={openTasks}><i className="dashboard-task-index">{String(index + 1).padStart(2, '0')}</i><span><b>{task.title}</b><small>{task.due_date ? formatDateLocale(task.due_date) : t('No deadline')}</small></span><ChevronRight size={16} /></button>)}{!pending.length && empty('All tasks are complete.')}</div><div className="dashboard-card-foot"><span>{tp('{n} open task|{n} open tasks', pending.length, { n: pending.length })}</span>{open('roadmap', 'View all', { tab: 'tasks' })}</div></>,
    meetings: <><div className="dashboard-card-list">{meetings.slice(0, 2).map((meeting) => <button key={meeting.id} onClick={() => setPage('bookings')}><CalendarClock size={20} /><span><b>{meeting.topic || t('Meeting')}</b><small>{dateTimeText(meeting.starts_at)}</small></span><ChevronRight size={16} /></button>)}{!meetings.length && <div className="dashboard-meeting-empty"><CalendarClock size={28} strokeWidth={1.3} />{empty('No upcoming meetings.')}<small>{t('Make time for your next step.')}</small></div>}</div>{open('bookings', meetings.length ? 'View all' : 'Request a meeting')}</>,
    applications: <><div className="dashboard-number">{numbers.applicationsTotal}<small>{t('Universities on your list')}</small></div><div className="dashboard-application-stats"><span><b>{numbers.applicationsSubmitted}</b>{t('Submitted')}</span><span><b>{data.essays.length}</b>{t('Essays')}</span><span><b>{numbers.applicationsAccepted}</b>{t('Accepted')}</span><span><b>{numbers.achievementsTotal}</b>{t('Achievements')}</span></div>{open('applications', 'View applications')}</>,
    discovery: <div className="dashboard-discovery-editorial"><button onClick={() => setPage('find_personality')}><span className="discovery-tool-heading"><Fingerprint size={22} /><ArrowUpRight size={17} /></span><b>{t('Profile Assessment')}</b><p>{t('Discover your strengths and study interests.')}</p><span className="discovery-tool-action">{t('Open assessment')}<ChevronRight size={13} /></span></button><button onClick={() => setPage('college_search')}><span className="discovery-tool-heading"><GraduationCap size={22} /><ArrowUpRight size={17} /></span><b>{t('College Search')}</b><p>{t('Compare universities with your goals.')}</p><span className="discovery-tool-action">{t('Find universities')}<ChevronRight size={13} /></span></button></div>,
    team: <><div className="dashboard-card-list">{data.team.slice(0, 2).map((member) => <button key={`${member.kind}-${member.id}`} onClick={() => onDirect(member.id)}><span className="dashboard-initial">{member.name?.charAt(0)}</span><span><b>{member.name}</b><small>{t(member.role)}</small></span><MessageCircle size={16} /></button>)}{!data.team.length && empty('No team members have been assigned yet.')}</div>{open('messages', 'Open messages')}</>,
  };
  return <section className="compact-dashboard reference-dashboard">
    <header className="dashboard-heading"><div className="dashboard-greeting"><span className="dashboard-wave" aria-hidden="true">👋</span><h2>{t('Hello')}, {name}</h2></div><div className="dashboard-heading-actions"><button className="button quiet small" onClick={() => { setDraft(preferences); setCustomizing(true); }}><SlidersHorizontal size={16} />{t('Customize')}</button></div></header>
    {saveError && <p role="status">{t('Changes apply now, but could not be saved in this browser.')}</p>}
    <div className={`dashboard-board dashboard-board-columns ${preferences.order.some((id) => !preferences.hidden.includes(id) && preferences.rail.includes(id)) ? 'has-rail' : ''} ${preferences.order.some((id) => !preferences.hidden.includes(id) && !preferences.rail.includes(id)) ? 'has-main' : ''}`}>{['main', 'rail'].map((column) => { const ids = preferences.order.filter((id) => !preferences.hidden.includes(id) && (column === 'rail' ? preferences.rail.includes(id) : !preferences.rail.includes(id))); return ids.length > 0 && <div key={column} className={`dashboard-column dashboard-column-${column} ${ids.length > (column === 'rail' ? 2 : 6) ? 'dense' : ''} ${column === 'main' && ids.length % 2 === 1 ? 'has-wide-last' : ''} ${column === 'main' && ids.length >= 3 && ids.length % 2 === 1 && ids.at(-1) === 'team' ? 'has-team-footer' : ''} ${column === 'rail' && ids.length === 2 && ids[0] === 'roadmap' ? 'roadmap-first' : ''} ${column === 'rail' && ids.length > 3 ? 'crowded' : ''}`} style={{'--widget-rows': Math.ceil(ids.length / (column === 'main' || ids.length > 3 ? 2 : 1))}}>{ids.map((id, index) => { const [title, Icon] = widgetMeta[id]; return <article key={id} className={`dashboard-tile dashboard-tile-${id} dashboard-position-${column === 'rail' ? index + 2 : index}`}><header><Icon size={18} /><h3>{t(title)}</h3></header>{content[id]}</article>; })}</div>; })}</div>
    {usageOpen && <Modal title={t('Program usage')} onClose={() => setUsageOpen(false)}>{data.programServices.length ? programUsage : <p className="dashboard-empty">{t('No program services have been assigned yet.')}</p>}</Modal>}
    {customizing && <DashboardCustomizer draft={draft} setDraft={setDraft} metadata={widgetMeta} Modal={Modal} onClose={() => setCustomizing(false)} onSave={save} />}
  </section>;
}
