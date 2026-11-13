import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowUpRight, CalendarClock, Check, Clock3, Fingerprint, Globe2, GraduationCap, Lock, MessageCircle, PenLine, Plus, School, SlidersHorizontal, Star, Target, Telescope, Upload, UsersRound, Map as MapIcon } from 'lucide-react';
import { t, tp, tx, formatDateLocale, formatNumberLocale, parseDateValue } from './i18n';
import { dateTimeText, dayMonthText, joinParts } from './lib/format';
import { daysUntil } from './lib/college';
import { isOpenTask, nextPriorities, studentProgress } from './lib/metrics';
import { upcomingMeetings } from './lib/meetings';
import { normalizeDashboardPreferences } from './dashboardPreferences';
import './dashboard.css';
import './design/pages/dashboard-blue.css';
import DashboardScreenTime from './DashboardScreenTime';
import { createPoller } from './lib/poller';
import { listText } from './lib/profileSections';
import { isPageLocked } from './lib/routes';
import DashboardCustomizer from './DashboardCustomizer';
import { ResourceContent } from './components/ResourceContent';
import { cachedDashboardLayout, loadAccountDashboardLayout, saveAccountDashboardLayout, subscribeDashboardLayout, pendingDashboardLayout } from './dashboardLayout';
import { Avatar, BlueButton, CardLink, Chip, DateTile, DaysChip, GlassCard, HeaderTools, KpiRow, KpiTile, PageHeader, SectionTitle } from './design/blue/ui';

const widgetMeta = {
  screen_time: ['Screen Time', Clock3],
  journey: ['Study goal', Target], tasks: ['Next priorities', Target],
  meetings: ['Meetings', CalendarClock], applications: ['Applications', GraduationCap],
  discovery: ['Student discovery tools', Telescope], team: ['My Naseeb team', UsersRound],
  programs: ['Programs', Globe2],
};

// The order of the blue board until the student customizes it: goal, priorities and deadlines, meetings, applications, programs, then the lower row.
const DEFAULT_BOARD_ORDER = ['journey', 'tasks', 'meetings', 'applications', 'programs', 'screen_time', 'discovery', 'team'];

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

// The day / month a DateTile shows ("Sep", never "Sept").
function tileParts(value) {
  const date = parseDateValue(value);
  if (Number.isNaN(date.getTime())) return { day: '', month: '' };
  return { day: String(date.getDate()), month: formatDateLocale(value, { month: 'short' }).replace(/\bSept\b/, 'Sep').replace(/\.$/, '') };
}

const STOP_WORDS = new Set(['the', 'of', 'and', 'at', 'in', 'for', 'de', 'la']);
// "The Chinese University of Hong Kong" -> "CUHK".
function universityInitials(name) {
  const words = String(name || '').split(/[\s\-–—,]+/).filter((word) => word && !STOP_WORDS.has(word.toLowerCase()));
  if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
  return words.map((word) => word[0]).join('').slice(0, 4).toUpperCase();
}

// Programs still taking applications, nearest deadline first; most of the
// catalog only has a yearly text deadline, so those count toward the total only.
function openProgramsOf(programs) {
  return programs
    .map((item) => [item, daysUntil(item.deadline)])
    .filter(([, days]) => days != null && days >= 0)
    .sort(([, a], [, b]) => a - b)
    .map(([item, days]) => ({ item, days }));
}

// The catalog is large, so this card fetches it itself instead of holding up the dashboard.
function ProgramsCard({ programs, status, load, retry, setPage, locked }) {
  useEffect(() => { load(); }, [load]);
  const open = useMemo(() => openProgramsOf(programs), [programs]);
  const featured = open[0];
  const explore = locked
    ? <button type="button" className="nb-dash-wide-btn is-light" disabled aria-disabled="true" title={t('Coming soon')} aria-label={`${t('Explore programs')} — ${t('Coming soon')}`}>{t('Coming soon')}<Lock size={16} aria-hidden="true" /></button>
    : <button type="button" className="nb-dash-wide-btn is-light" onClick={() => setPage('programs')}>{t('Explore programs')}<ArrowUpRight size={17} aria-hidden="true" /></button>;
  let body;
  if (status?.status === 'error' && !status.loaded) body = <div role="alert" className="nb-dash-error">{status.error}<button type="button" onClick={retry}>{t('Retry')}</button></div>;
  else if (!status?.loaded) body = <p role="status" className="nb-dash-note">{t('Loading…')}</p>;
  else body = <>
    <div className="nb-dash-programs-count"><b><CountUp value={open.length || programs.length} format={formatNumberLocale} /></b><span>{open.length ? t('Open for applications') : t('Programs in the catalog')}</span></div>
    {featured && <div className="nb-dash-featured">
      <DateTile hot={false} {...tileParts(featured.item.deadline)} className="nb-dash-featured-date" />
      <div><b>{featured.item.title}</b><small>{joinParts(featured.item.provider, dayMonthText(featured.item.deadline))}</small></div>
      <Chip variant="gold">{tp('{n} day left|{n} days left', featured.days, { n: featured.days })}</Chip>
    </div>}
    {open.length > 1 && <ul className="nb-dash-program-rows">{open.slice(1, 4).map(({ item, days }) => <li key={item.id}>
      <time dateTime={item.deadline}>{dayMonthText(item.deadline)}</time><span>{item.title}</span><em>{tp('{n} day left|{n} days left', days, { n: days })}</em>
    </li>)}</ul>}
  </>;
  return <GlassCard tone="hero" className="nb-dash-programs" title={t('Programs')} icon={Globe2} footer={explore}>{body}</GlassCard>;
}

// Open tasks with a date, and programs still taking applications, nearest first.
function buildDeadlines(tasks, programs) {
  const items = [];
  for (const task of tasks) {
    if (!isOpenTask(task)) continue;
    const days = daysUntil(task.due_date);
    if (days == null) continue;
    items.push({ key: `task-${task.id}`, title: task.title, sub: joinParts(t('Task'), task.assigned_by_name), date: task.due_date, days, page: 'tasks' });
  }
  for (const { item, days } of openProgramsOf(programs)) items.push({ key: `program-${item.id}`, title: item.title, sub: item.provider, date: item.deadline, days, page: 'programs' });
  items.sort((a, b) => a.days - b.days);
  return items;
}

function DeadlinesCard({ items, openPage, locked }) {
  const overdue = items.filter((item) => item.days < 0);
  const upcoming = items.filter((item) => item.days >= 0);
  const first = overdue[0];
  const review = () => openPage(first.page);
  return <GlassCard className="nb-dash-deadlines" title={t('Deadlines')} icon={Target} action={items.length ? <span className="nb-dash-count">{formatNumberLocale(items.length)}</span> : null}
    footer={<><span /><DeadlineLink locked={locked.tasks} onClick={() => openPage('tasks')}>{t('Open tasks')}</DeadlineLink></>}>
    {overdue.length > 0 && <button type="button" className="nb-dash-overdue" onClick={review} disabled={locked[first.page]}>
      <AlertCircle size={18} aria-hidden="true" />
      <span><b>{tp('{n} overdue deadline|{n} overdue deadlines', overdue.length, { n: overdue.length })}</b><small>{first.title}</small></span>
      <em>{t('Review now')}</em>
    </button>}
    {upcoming.length > 0 && <ul className="nb-dash-deadline-list">{upcoming.slice(0, 4).map((item) => <li key={item.key}>
      <DateTile hot={item.days <= 3} {...tileParts(item.date)} />
      <span className="nb-dash-row-copy"><b>{item.title}</b><small>{item.sub}</small></span>
      <DaysChip days={item.days} />
    </li>)}</ul>}
    {!items.length && <p className="nb-dash-note">{t('No deadlines coming up.')}</p>}
  </GlassCard>;
}

function DeadlineLink({ locked, onClick, children }) {
  return locked ? <span className="nb-card-link is-locked" aria-disabled="true">{t('Coming soon')}<Lock size={14} aria-hidden="true" /></span> : <CardLink onClick={onClick}>{children}</CardLink>;
}

export default function CompactDashboard({ user, student, data, setPage, onDirect, Modal, programUsage, programsStatus, loadPrograms, retryPrograms, resourceStatus, retryResources }) {
  // This browser's copy first, then the account's layout (see dashboardLayout.js).
  const [preferences, setPreferences] = useState(() => normalizeDashboardPreferences(cachedDashboardLayout(user.id)));
  useEffect(() => {
    let active = true;
    const unsubscribe = subscribeDashboardLayout(user.id, ({ layout, pending }) => { setPreferences(layout); setSaveError(pending); });
    loadAccountDashboardLayout(user.id).then((layout) => { if (active) setPreferences(layout); });
    return () => { active = false; unsubscribe(); };
  }, [user.id]);
  const [usageOpen, setUsageOpen] = useState(false);
  const [customizing, setCustomizing] = useState(false);
  const [draft, setDraft] = useState(preferences);
  const [saveError, setSaveError] = useState(false);
  useEffect(() => {
    if (!saveError) return undefined;
    const loop = createPoller({ min: 15_000, failureCap: 60_000, run: async () => {
      if (navigator.onLine === false) return null;
      await loadAccountDashboardLayout(user.id);
      return pendingDashboardLayout(user.id) ? null : true;
    } });
    const online = () => loop.poke();
    window.addEventListener('online', online);
    loop.start();
    return () => { loop.stop(); window.removeEventListener('online', online); };
  }, [saveError, user.id]);
  const pending = nextPriorities(data.tasks);
  const numbers = studentProgress(student);
  const stars = numbers.missionsApproved;
  const meetings = upcomingMeetings(data.bookings);
  const name = user.first_name || user.username;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const tasksReady = Boolean(resourceStatus?.tasks?.loaded);
  const studentReady = Boolean(resourceStatus?.students?.loaded);
  const locked = { tasks: isPageLocked('tasks', user), applications: isPageLocked('applications', user), roadmap: isPageLocked('roadmap', user), bookings: isPageLocked('bookings', user), programs: isPageLocked('programs', user), student_center: isPageLocked('student_center', user), messages: isPageLocked('messages', user) };
  const openPage = (page, params) => { if (!isPageLocked(page, user)) setPage(page, params); };
  function save() {
    const layout = draft;
    setPreferences(layout);
    setCustomizing(false);
    setSaveError(false);
    saveAccountDashboardLayout(user.id, layout);
  }

  // A link to another page, or the "Coming soon" lock when the page is not open yet.
  const link = (page, text, params) => isPageLocked(page, user)
    ? <span className="nb-card-link is-locked" aria-disabled="true" title={t('Coming soon')} aria-label={`${t(text)} — ${t('Coming soon')}`}>{t('Coming soon')}<Lock size={14} aria-hidden="true" /></span>
    : <CardLink onClick={() => setPage(page, params)}>{t(text)}</CardLink>;
  const empty = (text) => <p className="nb-dash-note">{t(text)}</p>;
  const programsLoaded = Boolean(programsStatus?.loaded);
  const deadlines = buildDeadlines(data.tasks, programsLoaded ? data.opportunityPrograms : []);
  const dependencies = { journey: ['students'], tasks: ['tasks'], meetings: ['bookings'], applications: ['students', 'essays'], team: ['team'] };
  const wrap = (id, children) => (dependencies[id] ? <ResourceContent keys={dependencies[id]} statuses={resourceStatus} retry={retryResources}>{children}</ResourceContent> : children);
  const card = (id, props, children) => {
    const [title, icon] = widgetMeta[id];
    const { className = '', ...rest } = props;
    return <GlassCard {...rest} className={`nb-dash-card nb-dash-card-${id} ${className}`.trim()} title={t(title)} icon={icon}>{wrap(id, children)}</GlassCard>;
  };

  const widgets = {
    journey: () => <section className="nb-card nb-dash-goal" aria-label={t('Study goal')}>
      {wrap('journey', <>
        <button type="button" className="nb-dash-goal-icon" onClick={() => openPage('student_center', { edit: 'goal' })} aria-label={t('Edit study goal')} disabled={locked.student_center}>{student?.target_major ? <GraduationCap size={26} aria-hidden="true" /> : <Plus size={26} aria-hidden="true" />}</button>
        <div className="nb-dash-goal-copy">
          <small>{t('Study goal')}</small>
          <h3>{student?.target_major || t('Set your study goal')}</h3>
        </div>
        <p className="nb-dash-goal-where"><Globe2 size={16} aria-hidden="true" />{listText(student?.target_countries) || t('Choose your study interests and destination.')}</p>
        <div className="nb-dash-goal-actions">
          {!locked.roadmap && <Chip variant="default" icon={Star} className="nb-dash-level">{tx`Level ${student?.level || 1}`} · {tp('{n} star|{n} stars', stars, { n: stars })}</Chip>}
          <BlueButton variant="ghost" size="sm" iconRight={ArrowUpRight} onClick={() => setUsageOpen(true)}>{t('Program usage')}</BlueButton>
          {!locked.student_center && <BlueButton variant="ghost" size="sm" className="nb-dash-edit-goal" arrow onClick={() => setPage('student_center', { edit: 'goal' })}>{t('Edit study goal')}</BlueButton>}
        </div>
      </>)}
    </section>,
    tasks: (rail) => <div className={`nb-dash-pair${rail ? ' is-stacked' : ''}`}>
      {wrap('tasks', <>
        <GlassCard className="nb-dash-card nb-dash-card-tasks" title={t('Next priorities')} icon={Target} footer={<><span>{tp('{n} open task|{n} open tasks', pending.length, { n: pending.length })}</span>{link('tasks', 'View all')}</>}>
          <ol className="nb-dash-priorities">{pending.slice(0, 3).map((task, index) => <li key={task.id}>
            <button type="button" onClick={() => openPage('tasks')} disabled={locked.tasks}><i>{String(index + 1).padStart(2, '0')}</i><span><b>{task.title}</b><small>{task.due_date ? formatDateLocale(task.due_date) : t('No deadline')}</small></span></button>
          </li>)}</ol>
          {!pending.length && empty('All tasks are complete.')}
        </GlassCard>
        <DeadlinesCard items={deadlines} openPage={openPage} locked={locked} />
      </>)}
    </div>,
    meetings: () => card('meetings', { footer: <><span />{link('bookings', meetings.length ? 'View all' : 'Request a meeting')}</> }, <>
      {meetings.length > 0 && <ul className="nb-dash-meeting-list">{meetings.slice(0, 2).map((meeting) => <li key={meeting.id}>
        <button type="button" onClick={() => openPage('bookings')} disabled={locked.bookings}><DateTile {...tileParts(meeting.starts_at)} /><span className="nb-dash-row-copy"><b>{meeting.topic || t('Meeting')}</b><small>{dateTimeText(meeting.starts_at)}</small></span></button>
      </li>)}</ul>}
      {!meetings.length && <div className="nb-dash-meeting-empty"><CalendarClock size={34} strokeWidth={1.4} aria-hidden="true" />{empty('No upcoming meetings.')}<p className="nb-dash-note">{t('Make time for your next step.')}</p></div>}
    </>),
    applications: (rail) => {
      const universities = (data.applications || []).map((application) => application.university_detail?.name).filter(Boolean);
      return card('applications', { className: rail ? 'is-rail' : '' }, <>
        <div className="nb-dash-apps-top">
          <div className="nb-dash-big"><b><CountUp value={numbers.applicationsTotal} format={formatNumberLocale} /></b><span>{t('Universities on your list')}</span></div>
          {universities.length > 0 && <ul className="nb-dash-uni-stack" aria-label={universities.join(', ')}>{universities.slice(0, 4).map((university, index) => <li key={`${university}-${index}`} aria-hidden="true">{universityInitials(university)}</li>)}</ul>}
        </div>
        <div className="nb-dash-apptiles">
          {[[Upload, numbers.applicationsSubmitted, 'Submitted'], [PenLine, data.essays.length, 'Essays'], [Check, numbers.applicationsAccepted, 'Accepted'], [Star, numbers.achievementsTotal, 'Achievements']].map(([Icon, value, text], index) => <div key={text} className={`nb-dash-apptile nb-kpi-tone-${index}`}>
            <span className="nb-dash-apptile-icon"><Icon size={18} aria-hidden="true" /></span><b>{formatNumberLocale(value)}</b><span>{t(text)}</span>
          </div>)}
        </div>
        {locked.applications
          ? <button type="button" className="nb-dash-wide-btn" disabled aria-disabled="true" title={t('Coming soon')} aria-label={`${t('View applications')} — ${t('Coming soon')}`}>{t('Coming soon')}<Lock size={16} aria-hidden="true" /></button>
          : <button type="button" className="nb-dash-wide-btn" onClick={() => setPage('applications')}>{t('View applications')}<ArrowUpRight size={17} aria-hidden="true" /></button>}
      </>);
    },
    programs: () => <ProgramsCard programs={data.opportunityPrograms} status={programsStatus} load={loadPrograms} retry={retryPrograms} setPage={setPage} locked={locked.programs} />,
    screen_time: () => card('screen_time', {}, <DashboardScreenTime userId={user.id} />),
    discovery: () => card('discovery', {}, <div className="nb-dash-tools">
      {[[Fingerprint, 'Profile Assessment', 'Discover your strengths and study interests.', 'find_personality'], [School, 'College Search', 'Compare universities with your goals.', 'college_search']].map(([Icon, title, text, page]) => <button key={page} type="button" onClick={() => setPage(page)}>
        <span className="nb-dash-tool-icon"><Icon size={22} aria-hidden="true" /></span><span className="nb-dash-row-copy"><b>{t(title)}</b><small>{t(text)}</small></span><ArrowUpRight size={16} aria-hidden="true" />
      </button>)}
    </div>),
    team: () => card('team', { footer: <><span />{link('messages', 'Open messages')}</> }, <>
      <ul className="nb-dash-team-list">{data.team.slice(0, 3).map((member) => <li key={`${member.kind}-${member.id}`}>
        <Avatar name={member.name} size={40} />
        <span className="nb-dash-row-copy"><b>{member.name}</b><small>{t(member.role)}</small></span>
        <button type="button" className="nb-dash-icon-btn" onClick={() => onDirect(member.id)} aria-label={`${t('Message')}: ${member.name}`} title={`${t('Message')}: ${member.name}`}><MessageCircle size={17} aria-hidden="true" /></button>
      </li>)}</ul>
      {!data.team.length && empty('No team members have been assigned yet.')}
    </>),
  };

  const { hidden, rail } = preferences;
  // Nobody has arranged the board yet: show the designed reading order.
  const untouched = JSON.stringify(preferences) === JSON.stringify(normalizeDashboardPreferences());
  const order = untouched ? DEFAULT_BOARD_ORDER.filter((id) => preferences.order.includes(id)) : preferences.order;
  const shown = order.filter((id) => !hidden.includes(id) && widgets[id]);
  const kpis = [
    { icon: Target, value: <CountUp value={pending.length} format={formatNumberLocale} />, label: t('Open tasks'), page: 'tasks', go: () => setPage('tasks'), ready: tasksReady },
    { icon: GraduationCap, value: <CountUp value={numbers.applicationsTotal} format={formatNumberLocale} />, label: t('Universities on your list'), page: 'applications', go: () => setPage('applications'), ready: studentReady },
    { icon: MapIcon, value: <CountUp value={numbers.roadmapPercent} format={(n) => `${formatNumberLocale(n)}%`} />, label: t('Roadmap'), page: 'roadmap', go: () => setPage('roadmap', {}), ready: studentReady },
  ].filter((kpi) => kpi.page !== 'roadmap' || !locked.roadmap);
  const subtitle = joinParts(formatDateLocale(new Date(), { weekday: 'long', day: 'numeric', month: 'long' }), tasksReady ? tp('{n} task open|{n} tasks open', pending.length, { n: pending.length }) : '');

  return <section className="nb-dash">
    <PageHeader title={<>{t(greeting)}, <b>{name}</b></>} subtitle={subtitle} />
    <HeaderTools><button type="button" className="nb-control" onClick={() => { setDraft(preferences); setCustomizing(true); }}><SlidersHorizontal size={17} aria-hidden="true" /><span className="nb-control-label">{t('Customize')}</span></button></HeaderTools>
    {saveError && <p role="status" className="nb-dash-save-error">{t('Your layout is not saved to your account yet. We will keep trying while this page is open.')}</p>}
    <KpiRow label={t('Summary')} columns={kpis.length} className="nb-dash-kpis">
      {kpis.map((kpi, index) => <KpiTile key={kpi.page} tone={index} icon={kpi.icon} value={kpi.value} label={kpi.label} loading={!kpi.ready}
        onClick={locked[kpi.page] ? undefined : kpi.go} actionLabel={locked[kpi.page] ? undefined : kpi.label} />)}
    </KpiRow>
    <SectionTitle className="nb-dash-activity">{t('My activity')}</SectionTitle>
    <div className="nb-dash-board">
      {shown.map((id) => <div key={id} className={`nb-dash-w nb-dash-w-${id}${rail.includes(id) ? ' is-rail' : ''}`} data-widget={id}>{widgets[id](rail.includes(id))}</div>)}
    </div>
    {usageOpen && <Modal title={t('Program usage')} onClose={() => setUsageOpen(false)}><ResourceContent keys={['programServices']} statuses={resourceStatus} retry={retryResources}>{data.programServices.length ? programUsage : <p className="dashboard-empty">{t('No program services have been assigned yet.')}</p>}</ResourceContent></Modal>}
    {customizing && <DashboardCustomizer draft={draft} setDraft={setDraft} metadata={widgetMeta} Modal={Modal} onClose={() => setCustomizing(false)} onSave={save} />}
  </section>;
}
