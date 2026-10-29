import { Stat, StudentTable, Record } from '../components/records';
import { t, tx, tp, formatNumberLocale, formatPercentLocale, formatDateLocale } from '../i18n';
import { Panel, Empty, Modal } from '../components/ui';
import { ChevronRight, Plus, SlidersHorizontal } from 'lucide-react';
import { studentName, dateText, joinParts, programUsageCaption } from '../lib/format';
import { isCounselor } from '../lib/roles';
import CompactDashboard from '../CompactDashboard';
import { ownStudent, label } from '../lib/labels';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { Field, CheckboxControl } from '../components/forms';
import { usePagedList } from '../hooks/usePagedList';
import { StudentPicker } from '../components/paged';
import { REVIEW_SOURCE, REVIEW_SOURCES } from '../lib/reviewQueue';
import { isPageLocked } from '../lib/routes';
import { reviewCounts, statsBadges } from '../lib/counselorCounts';
import { isExpiredMeeting } from '../lib/meetings';
import { CxHead } from '../components/counselorUi';
import { AllSetOverlay, CheckInsCard, CustomizeHome, DeadlinesCard, HomeError, HomeSkeleton, NeedYouCard, ReviewCard, SnapshotCard, StatCards, TodayCard } from '../components/counselorHome';
import { WIDE_CARDS, addCheckedIn, allClear, allSetSeen, checkInKey, checkInOutcome, checkInPage, greetingKey, loadLayout, markAllSetSeen, mergeCheckInRows, moveCard, normalizeLayout, saveLayout, setCheckIn, setCheckInRow, snapshotChoices, toggleCard, visibleCards, withPending } from '../lib/counselorHome';
import './counselor-home.css';
import { MeetingNoteForm } from './BookingsPage';
import { inServerZone } from '../lib/serverTime';

// The first screen of staff dashboards: a page of students and the nearest
// deadlines, fetched from the server rather than the whole roster.
function useDashboardLists(user) {
  const staff = user.role !== 'student';
  const students = usePagedList('students', { ordering: 'name', pageSize: 10, enabled: staff });
  // Open work only: approved or submitted tasks are not deadlines anyone must act on.
  const tasks = usePagedList('tasks', { ordering: 'due', filters: { open: 'true' }, pageSize: 6, enabled: staff && user.role !== 'organization' });
  return { students, tasks };
}

export function Dashboard({ user, data, stats, reload, notify, setPage, onDirect, resourceStatus, loadResources, retryResources, refreshStats, updateStats }) {
  if (user.role === 'student') return <StudentDashboard {...{ user, data, setPage, onDirect, resourceStatus, loadResources, retryResources }} />;
  return <StaffDashboard {...{ user, data, stats, reload, notify, setPage, refreshStats, updateStats }} />;
}

function StaffDashboard({ user, data, stats, reload, notify, setPage, refreshStats, updateStats }) {
  if (user.role === 'organization') return <OrganizationDashboard {...{ user, data, stats, setPage }} />;
  if (isCounselor(user)) return <CounselorHome {...{ user, stats, notify, setPage, refreshStats, updateStats }} />;
  return <TeacherDashboard {...{ user, data, stats, reload, notify, setPage }} />;
}

function OrganizationDashboard({ user, data, stats, setPage }) {
  const { students } = useDashboardLists(user);
  return <>
    <div className="stat-grid"><Stat label={t("School students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} note={t("Only students from your school")} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} note={t("Weighted completion")} /><Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} note={t("Mission completion")} /><Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} note={t("Late task or mission")} tone="danger" /></div>
    <Panel title={t("Student progress")} action={<button className="button primary" onClick={() => setPage('students')}>{t("Student profiles")} <ChevronRight size={17} /></button>}><StudentTable data={data} students={students.items} readOnly /></Panel>
  </>;
}

// Today: counselor and teacher, once teacher gets its own "Today's queue" (S3.7).
function TeacherDashboard({ user, data, stats, reload, notify, setPage }) {
  const { students, tasks } = useDashboardLists(user);
  const roadmapVisible = !isPageLocked('roadmap', user);
  return <>
    <div className="stat-grid"><Stat label={t("Students")} value={formatNumberLocale(stats?.students_total ?? students.items.length)} /><Stat label={t("Task progress")} value={formatPercentLocale(stats?.average_task_progress ?? 0)} />{roadmapVisible && <Stat label={t("Roadmap progress")} value={formatPercentLocale(stats?.average_roadmap_progress ?? 0)} />}<Stat label={t("Need attention")} value={formatNumberLocale(stats?.students_at_risk ?? 0)} tone="danger" /></div>
    <div className="split-grid wide-left"><Panel title={t("Student progress")} action={<button className="button quiet" onClick={() => setPage('students')}>{t("View all")} <ChevronRight size={16} /></button>}><StudentTable data={data} students={students.items} readOnly roadmapVisible={roadmapVisible} /></Panel><div className="section-stack"><Panel title={t("Upcoming deadlines")}>{tasks.items.map((task) => <Record key={task.id} title={task.title} meta={joinParts(task.student_name || studentName(data, task.student), task.due_date && tx`Due ${dateText(task.due_date)}`)} badge={task.status} />)}{tasks.loaded && !tasks.items.length && <Empty text={t("No task deadlines yet.")} />}</Panel>{isCounselor(user) && <ProgramUsageSummary {...{ user, data, reload, notify }} />}</div></div>
  </>;
}

// Home fetches nothing of its own: GET /dashboard/stats/?include=home (see
// App.jsx workspaceStatsRequest) feeds both the cards and the sidebar badges,
// and the minute poll refreshes both.
function useCounselorHome(stats, refreshStats) {
  const [state, setState] = useState({ error: '', loading: false });
  const load = useCallback(async () => {
    setState({ loading: true, error: '' });
    try {
      await refreshStats();
      setState({ loading: false, error: '' });
    } catch (err) {
      setState({ loading: false, error: err.message || t("Check your connection and try again.") });
    }
  }, [refreshStats]);
  // Stats loaded on another page carry no (or an older) Home: fetch it once.
  const needsHome = !stats?.home || Boolean(stats.home_stale);
  const asked = useRef(false);
  useEffect(() => {
    if (!needsHome || asked.current) return;
    asked.current = true;
    load();
  }, [needsHome, load]);
  return { ...state, reload: load };
}

const CHECK_IN_PAGE = 50;

function useStudentSnapshot(studentId, enabled) {
  const [state, setState] = useState({ id: null, data: null, error: '', loading: false });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!enabled || studentId == null) return undefined;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState((current) => ({ id: studentId, data: current.id === studentId ? current.data : null, error: '', loading: true }));
      return api.counselorSnapshot(studentId);
    }).then((response) => {
      if (active) setState({ id: studentId, data: response?.snapshot || null, error: '', loading: false });
    }).catch((err) => {
      if (active) setState({ id: studentId, data: null, error: err.message || t("Check your connection and try again."), loading: false });
    });
    return () => { active = false; };
  }, [studentId, enabled, attempt]);
  const own = state.id === studentId ? state : { id: studentId, data: null, error: '', loading: true };
  return { ...own, retry: () => setAttempt((value) => value + 1) };
}

function CounselorHome({ user, stats, notify, setPage, refreshStats, updateStats }) {
  const { error, loading, reload } = useCounselorHome(stats, refreshStats);
  const [layout, setLayout] = useState(() => loadLayout(() => window.localStorage, user.id));
  const [customizing, setCustomizing] = useState(false);
  const [noteFor, setNoteFor] = useState(null);
  const [pendingCheckIns, setPendingCheckIns] = useState(() => new Set());
  const pendingKeys = useRef(new Set());
  const [moreRows, setMoreRowsState] = useState([]);
  const moreRowsRef = useRef([]);
  const [morePaging, setMorePaging] = useState({ loading: false, done: false });
  const [allSetClosed, setAllSetClosed] = useState(false);
  const [snapshotFor, setSnapshotFor] = useState(null);
  const home = stats?.home;
  const name = user.first_name || user.username;
  // The server's hour, like the date and week below (lib/serverTime).
  const greeting = t(greetingKey(inServerZone(new Date()).getHours()));

  function setMoreRows(rows) {
    moreRowsRef.current = rows;
    setMoreRowsState(rows);
  }

  function changeLayout(next) {
    setLayout(next);
    saveLayout(() => window.localStorage, user.id, next);
  }

  function applyCheckIn(studentId, dayIndex, checked, days = null) {
    if (moreRowsRef.current.some((row) => row.student === studentId)) {
      const { rows, delta } = setCheckInRow(moreRowsRef.current, studentId, dayIndex, checked, days);
      setMoreRows(rows);
      if (delta) updateStats((current) => (current?.home ? { ...current, home: { ...current.home, check_ins: addCheckedIn(current.home.check_ins, delta) } } : current));
      return;
    }
    updateStats((current) => (current?.home ? { ...current, home: { ...current.home, check_ins: setCheckIn(current.home.check_ins, studentId, dayIndex, checked, days) } } : current));
  }

  async function toggleCheckIn(studentId, dayIndex, checked) {
    const day = home.week[dayIndex];
    const key = checkInKey(studentId, day);
    if (pendingKeys.current.has(key)) return;
    pendingKeys.current.add(key);
    setPendingCheckIns((current) => withPending(current, key, true));
    applyCheckIn(studentId, dayIndex, checked);
    try {
      const outcome = checkInOutcome(await api.counselorCheckIn(studentId, day, checked), checked);
      applyCheckIn(studentId, dayIndex, outcome.checked, outcome.days);
    } catch (err) {
      applyCheckIn(studentId, dayIndex, !checked);
      notify(err.message, 'error');
    } finally {
      pendingKeys.current.delete(key);
      setPendingCheckIns((current) => withPending(current, key, false));
    }
  }

  const firstRows = home?.check_ins?.students || [];
  const checkInRows = mergeCheckInRows(firstRows, moreRows);
  const shown = visibleCards(layout);

  const snapshotOptions = snapshotChoices(home?.need_you?.students, checkInRows);
  const snapshotStudent = snapshotFor || snapshotOptions[0] || null;
  const snapshot = useStudentSnapshot(snapshotStudent?.id ?? null, Boolean(home) && shown.includes('snapshot'));

  const review = reviewCounts(stats);
  const storage = () => window.localStorage;
  // Every request waiting for the counselor, any day: the sidebar's Meetings badge.
  // Today's list is only the fallback for an API without badges.
  const pendingRequests = statsBadges(stats)?.meetings ?? (home?.meetings.today.filter((meeting) => meeting.status === 'pending' && !isExpiredMeeting(meeting)).length || 0);
  const essaysWaiting = Number(stats?.review?.essays) || 0;
  const nothingWaiting = Boolean(home) && allClear({ review: review.total, needYou: home.need_you.total, unread: home.messages.unread }) && !pendingRequests && !essaysWaiting;
  const showAllSet = nothingWaiting && !allSetClosed && !allSetSeen(storage, user.id, home.today);

  function closeAllSet() {
    markAllSetSeen(storage, user.id, home.today);
    setAllSetClosed(true);
  }

  const firstPage = checkInPage({ check_ins: home?.check_ins }, 0);
  const checkInsHaveMore = moreRows.length || morePaging.done ? !morePaging.done : firstPage.hasMore;

  async function loadMoreCheckIns() {
    if (morePaging.loading) return;
    const offset = checkInRows.length;
    setMorePaging({ loading: true, done: false });
    try {
      const page = checkInPage(await api.counselorCheckIns(offset, CHECK_IN_PAGE), offset);
      setMoreRows(mergeCheckInRows(moreRowsRef.current, page.rows.filter((row) => !firstRows.some((first) => first.student === row.student))));
      setMorePaging({ loading: false, done: !page.hasMore || !page.rows.length });
    } catch (err) {
      setMorePaging({ loading: false, done: false });
      notify(err.message, 'error');
    }
  }

  const head = (subtitle) => <CxHead title={<>{greeting}, <b className="ch-name">{name}</b></>} subtitle={subtitle}>
    <button type="button" className="cx-btn lg" onClick={() => setCustomizing(true)} disabled={!home}><SlidersHorizontal size={16} aria-hidden="true" />{t("Customize")}</button>
  </CxHead>;

  if (!home) {
    return <div className="cx-page ch-home">
      {head(null)}
      {error ? <HomeError message={error} onRetry={reload} /> : <HomeSkeleton />}
    </div>;
  }

  const breakdown = joinParts(...REVIEW_SOURCES.filter(({ kind }) => review[kind] > 0).map(({ kind, countPattern }) => tp(countPattern, review[kind], { n: review[kind] })));
  const meetingsToday = home.meetings.today.filter((meeting) => meeting.status !== 'pending');
  const openStudent = (studentId) => setPage('students', studentId ? { studentId } : {});
  const cards = {
    stats: <StatCards review={review} breakdown={breakdown} needYou={home.need_you.total} meetings={meetingsToday} requests={pendingRequests} messages={home.messages} setPage={setPage} />,
    review: <ReviewCard items={(home.review_items || []).filter((item) => REVIEW_SOURCE[item.kind])} total={review.total} onOpen={(item) => setPage('review', item ? { item: item.id } : {})} />,
    need_you: <NeedYouCard needYou={home.need_you} onOpen={openStudent} />,
    today: <TodayCard week={home.week} today={home.today} meetings={home.meetings} onOpenMeeting={() => setPage('bookings')} onNotes={setNoteFor} />,
    deadlines: <DeadlinesCard deadlines={home.deadlines} onOpenStudents={() => setPage('students')} />,
    check_ins: <CheckInsCard checkIns={{ ...home.check_ins, students: checkInRows }} week={home.week} today={home.today} onToggle={toggleCheckIn} pending={pendingCheckIns}
      hasMore={Boolean(checkInsHaveMore)} loadingMore={morePaging.loading} onLoadMore={loadMoreCheckIns} history={home.check_in_history} />,
    snapshot: <SnapshotCard choices={snapshotOptions} selected={snapshotStudent} onSelect={setSnapshotFor} state={snapshot} onRetry={snapshot.retry} onOpenStudent={openStudent} />,
  };
  return <div className="cx-page ch-home">
    {head(<>{formatDateLocale(home.today, { weekday: 'long', day: 'numeric', month: 'long' })} · {joinParts(
      tp('{n} thing to review|{n} things to review', review.total, { n: review.total }),
      tp('{n} meeting today|{n} meetings today', meetingsToday.length, { n: meetingsToday.length }),
    )}{pendingRequests > 0 && <> · <button type="button" className="cx-link ch-head-link" onClick={() => setPage('bookings')}>{tp('{n} request waiting|{n} requests waiting', pendingRequests, { n: pendingRequests })}</button></>}{loading && <span className="ch-refreshing" role="status"> · {t("Updating…")}</span>}</>)}
    {error && <HomeError message={error} onRetry={reload} />}
    <div className="ch-grid-cards">
      {shown.filter((id) => cards[id]).map((id) => <div key={id} className={`ch-slot ch-slot-${id}${WIDE_CARDS.includes(id) ? ' wide' : ''}`}>{cards[id]}</div>)}
    </div>
    {!shown.length && <p className="ch-empty">{t("Every card is hidden. Use Customize to show them again.")}</p>}
    {customizing && <CustomizeHome layout={layout}
      onToggle={(id) => changeLayout(toggleCard(layout, id))}
      onMove={(id, delta) => changeLayout(moveCard(layout, id, delta))}
      onReset={() => changeLayout(normalizeLayout(null))}
      onClose={() => setCustomizing(false)} />}
    {showAllSet && <AllSetOverlay onClose={closeAllSet} />}
    {noteFor && <MeetingNoteForm booking={noteFor} onClose={() => setNoteFor(null)} onSaved={() => { setNoteFor(null); reload(); }} notify={notify} />}
  </div>;
}

export function StudentDashboard({ user, data, setPage, onDirect, resourceStatus, loadResources, retryResources }) {
  const loadPrograms = useCallback(() => loadResources(['opportunityPrograms']), [loadResources]);
  const retryPrograms = useCallback(() => retryResources(['opportunityPrograms']), [retryResources]);
  return <CompactDashboard key={user.id} user={user} student={ownStudent(data)} data={data} setPage={setPage} onDirect={onDirect} Modal={Modal} programUsage={<ProgramUsageSummary user={user} data={data} />}
    resourceStatus={resourceStatus} retryResources={retryResources} programsStatus={resourceStatus?.opportunityPrograms} loadPrograms={loadPrograms} retryPrograms={retryPrograms} />;
}

export function ProgramServiceForm({ service, user, data, defaultStudentId = null, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  const [unlimited, setUnlimited] = useState(Boolean(service?.unlimited));
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      student: service?.student || Number(values.get('student')),
      name: values.get('name'),
      category: values.get('category'),
      status: values.get('status'),
      unlimited,
      total_hours: unlimited ? null : Number(values.get('total_hours')),
      used_hours: Number(values.get('used_hours') || 0),
      mentor: user.role === 'counselor' ? user.id : service?.mentor || null
    };
    try {
      if (service) await api.update('program-services', service.id, payload);else
      await api.create('program-services', payload);
      notify(service ? t("Program service updated.") : t("Program service assigned."));
      onSaved();
    } catch (err) {notify(err.message, 'error');} finally {setSaving(false);}
  }
  return <Modal title={service ? t("Edit program service") : t("Assign program service")} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <StudentPicker required value={service?.student || defaultStudentId || ''} selectedLabel={service?.student_name} disabled={Boolean(service)} hint={t("The currently selected student is preselected.")} />
    <Field label={t("Service name")}><input name="name" defaultValue={service?.name || ''} required /></Field>
    <Field label={t("Category")}><input name="category" defaultValue={service?.category || ''} placeholder={t("Essay, mentorship, admissions…")} /></Field>
    <Field label={t("Status")}><select name="status" defaultValue={service?.status || 'active'}>{['active', 'pending', 'completed'].map((status) => <option value={status} key={status}>{label(status)}</option>)}</select></Field>
    <Field label={t("Allocated hours")}><input name="total_hours" type="number" min="0.5" step="0.5" defaultValue={service?.total_hours || ''} required={!unlimited} disabled={unlimited} /></Field>
    <Field label={t("Used hours")}><input name="used_hours" type="number" min="0" step="0.5" defaultValue={service?.used_hours || 0} /></Field>
    <CheckboxControl className="form-wide" checked={unlimited} onChange={(event) => setUnlimited(event.target.checked)}>{t("Unlimited service access")}</CheckboxControl>
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving}>{saving ? t("Saving…") : t("Save service")}</button></div>
  </form></Modal>;
}

export function ProgramUsageSummary({ user, data, reload, notify }) {
  const manager = isCounselor(user);
  const [open, setOpen] = useState(false);
  const services = data.programServices;
  const finite = services.filter((item) => !item.unlimited);
  const total = finite.reduce((sum, item) => sum + Number(item.total_hours || 0), 0);
  const used = finite.reduce((sum, item) => sum + Number(item.used_hours || 0), 0);
  const remaining = Math.max(total - used, 0);
  const unlimited = services.filter((item) => item.unlimited).length;
  const share = total ? Math.round(remaining / total * 100) : 100;
  const hours = (value) => `${formatNumberLocale(value, { maximumFractionDigits: 1 })} ${t("h")}`;
  const visible = [...services].sort((a, b) => (a.status === 'active' ? 0 : 1) - (b.status === 'active' ? 0 : 1)).slice(0, 4);
  if (!manager && !services.length) return null;
  return <Panel title={t("Program usage")} action={manager ? <button className="button quiet small" onClick={() => setOpen(true)}><Plus size={14} /> {t("Assign service")}</button> : null}>
    <div className="usage-headline">
      <div className="usage-ring" style={{ '--progress': `${share}%` }} role="img" aria-label={total ? tx`${formatPercentLocale(share)} of hours remaining` : t("Unlimited access")}><strong>{total ? formatPercentLocale(share) : '\u221e'}</strong></div>
      <div className="usage-headline-copy">
        <strong>{total ? hours(remaining) : '\u221e'}</strong>
        <span>{total ? t("Remaining") : t("Unlimited access")}</span>
        <small>{programUsageCaption({ total, used, unlimited, hours })}</small>
      </div>
    </div>
    <div className="record-list usage-service-list">{visible.map((service) => <article className="record" key={service.id}><div className="record-main">
      <div><b>{service.name}</b><small>{manager && service.student_name ? `${service.student_name} \u00b7 ` : ''}{service.mentor_name || t("Mentor pending")}</small></div>
      <span className={`usage-service-value${service.unlimited ? ' is-unlimited' : ''}`}>{service.unlimited ? '\u221e' : hours(service.remaining_hours ?? 0)}</span>
    </div></article>)}{!visible.length && <Empty text={t("No program services have been assigned yet.")} />}</div>
    {open && <ProgramServiceForm user={user} data={data} notify={notify} onClose={() => setOpen(false)} onSaved={() => {setOpen(false);reload();}} />}
  </Panel>;
}
