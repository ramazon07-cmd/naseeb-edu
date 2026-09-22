import { useEffect, useState } from 'react';
import { CalendarClock, ChevronRight, Clock3, Fingerprint, GraduationCap, MessageCircle, SlidersHorizontal, Target, UsersRound, ArrowUpRight, Star, Map, Plus } from 'lucide-react';
import { api } from './api';
import { t, formatPercentLocale, formatDateLocale } from './i18n';
import { normalizeDashboardPreferences } from './dashboardPreferences';
import './dashboard.css';
import DashboardCustomizer from './DashboardCustomizer';

const widgetMeta = {
  journey: ['Study goal', Target], tasks: ['Next priorities', Target],
  meetings: ['Meetings', CalendarClock], applications: ['Applications', GraduationCap],
  discovery: ['Student discovery tools', Fingerprint], team: ['My Naseeb team', UsersRound], roadmap: ['Roadmap', Map],
};

export function ScreenTimeShortcut({ setPage, userId }) {
  const [seconds, setSeconds] = useState(null);
  useEffect(() => {
    let active = true;
    const load = () => { if (!document.hidden) api.screenTimeSummary(7).then((result) => { if (active) setSeconds(result.own?.today_seconds ?? 0); }).catch(() => { if (active) setSeconds(null); }); };
    load();
    const interval = window.setInterval(load, 60000);
    return () => { active = false; window.clearInterval(interval); };
  }, [userId]);
  return <button className="dashboard-time" onClick={() => setPage('screen_time')} title={t('Screen Time')}><Clock3 size={16} /><span>{t('Screen Time')}</span><b>{seconds === null ? '—' : `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`}</b><ChevronRight size={14} /></button>;
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
  const pending = data.tasks.filter((task) => task.status !== 'approved').sort((a, b) => (Date.parse(a.due_date) || Infinity) - (Date.parse(b.due_date) || Infinity));
  const approved = data.tasks.filter((task) => task.status === 'approved').length;
  const submitted = data.applications.filter((item) => ['submitted', 'accepted'].includes(item.status)).length;
  const meetings = data.bookings.filter((item) => new Date(item.starts_at) >= new Date() && !['cancelled', 'rejected', 'completed'].includes(item.status)).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
  const progress = Math.max(0, Math.min(100, Number(student?.journey_progress_percent) || 0));
  const name = user.first_name || user.username;
  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(draft)); setSaveError(false); } catch { setSaveError(true); }
    setPreferences(draft);
    setCustomizing(false);
  }
  const open = (page, text) => <button className="dashboard-link" onClick={() => setPage(page)}>{t(text)}<ChevronRight size={15} /></button>;
  const empty = (text) => <p className="dashboard-empty">{t(text)}</p>;
  const content = {
    journey: <><div className="dashboard-goal-body"><button className="dashboard-goal-symbol" onClick={() => setPage('profile')} aria-label={t('Edit study goal')}>{student?.target_major ? <GraduationCap size={32} strokeWidth={1.5} /> : <Plus size={30} />}</button><div><h4>{student?.target_major || t('Set your study goal')}</h4><p>{student?.target_countries || t('Choose your study interests and destination.')}</p><span className="dashboard-goal-pill"><Star size={13} />{t('Level')} {student?.level || 1}<span>·</span>{student?.roadmap_stars || 0} {t('Stars')}</span></div></div><div className="dashboard-goal-footer">{open('profile', 'Edit study goal')}<button className="dashboard-link" onClick={() => setUsageOpen(true)}>{t('Program usage')}<ArrowUpRight size={14} /></button></div></>,
    roadmap: <><div className="dashboard-roadmap-value"><strong>{formatPercentLocale(progress)}</strong><span>{t('Overall journey')}</span>{open('roadmap', 'Open roadmap')}</div><div className="dashboard-progress-track" role="progressbar" aria-label={t('Journey progress')} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{width: `${progress}%`}} /></div><p className="dashboard-roadmap-caption">{approved}/{data.tasks.length} {t('Tasks')}</p></>,
    tasks: <><div className="dashboard-card-list">{pending.slice(0, 3).map((task, index) => <button key={task.id} onClick={() => setPage('roadmap')}><i className="dashboard-task-index">{String(index + 1).padStart(2, '0')}</i><span><b>{task.title}</b><small>{task.due_date ? formatDateLocale(task.due_date) : t('No deadline')}</small></span><ChevronRight size={16} /></button>)}{!pending.length && empty('All tasks are complete.')}</div><div className="dashboard-card-foot"><span>{pending.length} {t('Active tasks')}</span>{open('roadmap', 'View all')}</div></>,
    meetings: <><div className="dashboard-card-list">{meetings.slice(0, 2).map((meeting) => <button key={meeting.id} onClick={() => setPage('bookings')}><CalendarClock size={20} /><span><b>{meeting.title || t('Meeting')}</b><small>{formatDateLocale(meeting.starts_at)} · {new Date(meeting.starts_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</small></span><ChevronRight size={16} /></button>)}{!meetings.length && <div className="dashboard-meeting-empty"><CalendarClock size={28} strokeWidth={1.3} />{empty('No upcoming meetings.')}<small>{t('Make time for your next step.')}</small></div>}</div>{open('bookings', 'Meetings')}</>,
    applications: <><div className="dashboard-number">{data.applications.length}<small>{t('Universities on your list')}</small></div><div className="dashboard-application-stats"><span><b>{submitted}</b>{t('Submitted')}</span><span><b>{data.essays.length}</b>{t('Essays')}</span><span><b>{data.applications.filter((item) => item.status === 'accepted').length}</b>{t('Accepted')}</span><span><b>{data.achievements.length + data.honors.length}</b>{t('Achievements')}</span></div>{open('applications', 'View applications')}</>,
    discovery: <div className="dashboard-discovery-editorial"><button onClick={() => setPage('find_personality')}><span className="discovery-tool-heading"><Fingerprint size={22} /><ArrowUpRight size={17} /></span><b>{t('Profile Assessment')}</b><p>{t('Discover your strengths and study interests.')}</p><span className="discovery-tool-action">{t('Open assessment')}<ChevronRight size={13} /></span></button><button onClick={() => setPage('college_search')}><span className="discovery-tool-heading"><GraduationCap size={22} /><ArrowUpRight size={17} /></span><b>{t('University Match')}</b><p>{t('Compare universities with your goals.')}</p><span className="discovery-tool-action">{t('Explore matches')}<ChevronRight size={13} /></span></button></div>,
    team: <><div className="dashboard-card-list">{data.team.slice(0, 2).map((member) => <button key={`${member.kind}-${member.id}`} onClick={() => onDirect(member.id)}><span className="dashboard-initial">{member.name?.charAt(0)}</span><span><b>{member.name}</b><small>{t(member.role)}</small></span><MessageCircle size={16} /></button>)}{!data.team.length && empty('No team members have been assigned yet.')}</div>{open('messages', 'Messages')}</>,
  };
  return <section className="compact-dashboard reference-dashboard">
    <header className="dashboard-heading"><div className="dashboard-greeting"><span className="dashboard-wave" aria-hidden="true">👋</span><h2>{t('Hello')}, {name}</h2></div><div className="dashboard-heading-actions"><ScreenTimeShortcut userId={user.id} setPage={setPage} /><button className="button quiet small" onClick={() => { setDraft(preferences); setCustomizing(true); }}><SlidersHorizontal size={16} />{t('Customize')}</button></div></header>
    {saveError && <p role="status">{t('Changes apply now, but could not be saved in this browser.')}</p>}
    <div className={`dashboard-board dashboard-board-columns ${preferences.order.some((id) => !preferences.hidden.includes(id) && preferences.rail.includes(id)) ? 'has-rail' : ''} ${preferences.order.some((id) => !preferences.hidden.includes(id) && !preferences.rail.includes(id)) ? 'has-main' : ''}`}>{['main', 'rail'].map((column) => { const ids = preferences.order.filter((id) => !preferences.hidden.includes(id) && (column === 'rail' ? preferences.rail.includes(id) : !preferences.rail.includes(id))); return ids.length > 0 && <div key={column} className={`dashboard-column dashboard-column-${column} ${ids.length > (column === 'rail' ? 2 : 5) ? 'dense' : ''} ${column === 'main' && ids.length % 2 === 1 ? 'has-wide-last' : ''} ${column === 'main' && ids.length >= 3 && ids.length % 2 === 1 && ids.at(-1) === 'team' ? 'has-team-footer' : ''} ${column === 'rail' && ids.length === 2 && ids[0] === 'roadmap' ? 'roadmap-first' : ''} ${column === 'rail' && ids.length > 3 ? 'crowded' : ''}`} style={{'--widget-rows': Math.ceil(ids.length / (column === 'main' || ids.length > 3 ? 2 : 1))}}>{ids.map((id, index) => { const [title, Icon] = widgetMeta[id]; return <article key={id} className={`dashboard-tile dashboard-tile-${id} dashboard-position-${column === 'rail' ? index + 2 : index}`}><header><Icon size={18} /><h3>{t(title)}</h3></header>{content[id]}</article>; })}</div>; })}</div>
    {usageOpen && <Modal title={t('Program usage')} onClose={() => setUsageOpen(false)}>{data.programServices.length ? programUsage : <p className="dashboard-empty">{t('No program services have been assigned yet.')}</p>}</Modal>}
    {customizing && <DashboardCustomizer draft={draft} setDraft={setDraft} metadata={widgetMeta} Modal={Modal} onClose={() => setCustomizing(false)} onSave={save} />}
  </section>;
}
