import { CounselorStudentTable as StudentTable, StatusTag, LateWork, targetText } from '../components/CounselorStudentTable';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Calendar, ChevronLeft, ChevronRight, LayoutGrid, MessageCircle, Plus, Rows3, Search, UserPlus, X } from 'lucide-react';
import { api } from '../api';
import { t, tp, tx, formatNumberLocale, formatPercentLocale } from '../i18n';
import { CxAccountActions, CxAvatar, CxCard, CxHead, CxPills, CxProgress, CxTabs, CxTag, ReasonTags } from '../components/counselorUi';
import { Field, SegmentedField } from '../components/forms';
import { Modal } from '../components/ui';
import { DocumentPreviewModal, TaskSubmissionModal } from '../components/documents';
import { LoadMore, PagedListError } from '../components/paged';
import { PageSkeleton } from '../components/states';
import { TemporaryCredentialModal } from '../components/TemporaryCredentialModal';
import { StudentQuickPanel } from '../components/StudentQuickPanel';
import { DownloadCvButton } from '../components/CvDocument';
import { mergeSaved } from '../lib/mergeSaved';
import { RecommendationLetters } from '../components/RecommendationLetters';
import { studentRecordEndpoints, useStudentRecords } from '../hooks/useStudentRecords';
import { invalidatePagedLists, usePagedList } from '../hooks/usePagedList';
import { activityText } from '../lib/activityText';
import { FILTER_GRADES, clockText, dateText, dateTimeText, dayLabel, dayMonthText, gradeOrPending, gradeText, joinParts, localDateKey, relativeDayText } from '../lib/format';
import { fullName, initials, label } from '../lib/labels';
import { createLatestRequest } from '../lib/latestRequest';
import { splitList } from '../lib/profileSections';
import { meetingBadgeStatus, meetingStatus, upcomingMeetings } from '../lib/meetings';
import { mergeReviewQueue } from '../lib/reviewQueue';
import { documentStatus, hasSubmission } from '../lib/reviewSubmission';
import { failedPage, pageAfterLoad, pageCount } from '../lib/studentListPage';
import { studentReasons } from '../lib/studentReasons';
import { BookingForm, MeetingNoteForm } from './BookingsPage';
import { ReviewWorkspace } from './ReviewPage';
import './counselor-students.css';
import { ParentInviteModal, StudentAssignmentModal, StudentForm } from './StudentsPage';

// A status word's colour: done and confirmed are green, waiting is amber, late or missing red.
const STATUS_TONE = { approved: 'ok', completed: 'ok', confirmed: 'ok', verified: 'ok', submitted: 'warn', uploaded: 'warn', reviewing: 'warn', pending: 'warn', late: 'late', rejected: 'late', required: 'late', expired_unconfirmed: 'quiet' };
const statusTone = (status) => STATUS_TONE[status] || 'quiet';

// One task, assigned to one or several students at once.
function BulkTaskForm({ studentIds, onClose, onSaved, notify }) {
  const [saving, setSaving] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const values = new FormData(event.currentTarget);
    const payload = { title: values.get('title'), due_date: values.get('due_date'), priority: values.get('priority') };
    try {
      // One request, all or nothing: a rejected student creates no task for anyone.
      const { created } = await api.bulkCreateTasks({ ...payload, students: studentIds });
      notify(tp('Task assigned to {n} student.|Task assigned to {n} students.', created, { n: created }));
      onSaved();
    } catch (failure) {
      notify(failure.message, 'error');
    } finally {
      setSaving(false);
    }
  }
  return <Modal title={tp('Assign task to {n} student|Assign task to {n} students', studentIds.length, { n: studentIds.length })} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <Field label={t("Task title")}><input name="title" required /></Field>
    <Field label={t("Due date")}><input name="due_date" type="date" required /></Field>
    <SegmentedField name="priority" label="Priority" value="medium" options={['low', 'medium', 'high', 'urgent'].map((value) => ({ value, label: label(value) }))} />
    <div className="form-actions"><button type="button" className="button quiet" onClick={onClose}>{t("Cancel")}</button><button className="button primary" disabled={saving} aria-busy={saving}>{saving ? t("Assigning…") : t("Assign task")}</button></div>
  </form></Modal>;
}

// "Students": who is assigned to you and what they need from you, one server page
// at a time (GET /api/students/?page=&status=&grade=&country=&ordering=).
const PAGE_SIZE = 25;
const VIEW_KEY = 'naseeb-counselor-students-view';
const STATUS_PILLS = [['all', 'All'], ['need_you', 'Need you'], ['late', 'Late work'], ['missing_documents', 'Missing documents'], ['quiet', 'Quiet for 14+ days'], ['on_track', 'On track']];
const SORTS = [['need_you', 'Needs you first'], ['late', 'Most late work'], ['name', 'Name A–Z']];
const COUNTRIES =['US', 'UK', 'Canada', 'Turkey', 'Vietnam', 'Hong Kong', 'China', 'Europe', 'Other'];
export const STUDENT_LIST_DEFAULTS = Object.freeze({ status: 'all', grade: '', country: '', ordering: 'need_you', page: 1, search: '' });

function readView() {
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'cards' ? 'cards' : 'table';
  } catch {
    return 'table';
  }
}

function saveView(view) {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // The choice just isn't remembered.
  }
}

// `flush(next)` sets the value at once and drops the pending one, so a cleared
// search never comes back from the timer.
function useDebounced(value, delay) {
  const [debounced, setDebounced] = useState(value);
  const timer = useRef(null);
  useEffect(() => {
    timer.current = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer.current);
  }, [value, delay]);
  const flush = useCallback((next) => {
    clearTimeout(timer.current);
    setDebounced(next);
  }, []);
  return [debounced, flush];
}

function filterParams(state) {
  const params = new URLSearchParams();
  if (state.search.trim()) params.set('search', state.search.trim());
  for (const key of ['grade', 'country']) if (state[key]) params.set(key, state[key]);
  return params;
}

// One page of students and the pill counts (GET /api/students/summary/).
function useStudentPage(state, version) {
  const [page, setPage] = useState({ key: '', items: [], count: 0, loading: true, error: '', status: 0 });
  const [summary, setSummary] = useState(null);
  const filters = filterParams(state);
  const summaryKey = `?${filters}`;
  const params = new URLSearchParams(filters);
  params.set('page', String(state.page));
  params.set('page_size', String(PAGE_SIZE));
  params.set('ordering', state.ordering);
  if (state.status !== 'all') params.set('status', state.status);
  const pageKey = `?${params}`;

  useEffect(() => {
    const controller = new AbortController();
    setPage((current) => ({ ...current, loading: true, error: '' }));
    api.page('students', pageKey, controller.signal).then(
      (result) => setPage({ key: pageKey, items: result?.results || [], count: result?.count ?? 0, loading: false, error: '', status: 0 }),
      (failure) => { if (!controller.signal.aborted) setPage(failedPage(pageKey, failure)); },
    );
    return () => controller.abort();
  }, [pageKey, version]);

  useEffect(() => {
    const controller = new AbortController();
    api.page('students/summary', summaryKey, controller.signal).then(setSummary, () => {});
    return () => controller.abort();
  }, [summaryKey, version]);

  return { ...page, summary, stale: page.key !== pageKey };
}


function StudentCards({ rows, selecting, selected, toggle, onPreview }) {
  return <div className="cs-cards">
    {rows.map(({ student, reasons, name }) => {
      const body = <>
        <span className="cs-card-top">
          <CxAvatar name={name} />
          <span className="cx-row-copy"><b>{name}</b><small>{joinParts(gradeOrPending(student.grade), targetText(student))}</small></span>
        </span>
        <span className="cs-card-foot"><LateWork reasons={reasons} /><StatusTag reasons={reasons} /></span>
      </>;
      return selecting
        ? <label key={student.id} className={`cs-card${selected.has(student.id) ? ' selected' : ''}`}><input type="checkbox" className="cs-card-check" checked={selected.has(student.id)} onChange={() => toggle(student.id)} aria-label={tx`Select ${name}`} />{body}</label>
        : <button key={student.id} type="button" className="cs-card" onClick={() => onPreview(student)} aria-label={t('Quick look at {name}', { name })}>{body}</button>;
    })}
  </div>;
}

function CounselorStudentList({ user, data, query, setQuery, listState, setListState, onItems, onOpen, onDirect, onAddStudent, notify, reload }) {
  const readOnly = user.role === 'assistant';
  const [view, setView] = useState(readView);
  const [version, setVersion] = useState(0);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [assigning, setAssigning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [adding, setAdding] = useState(false);
  const closePreview = useCallback(() => setPreview(null), []);
  const [search, flushSearch] = useDebounced(query, 250);
  const state = listState;
  const update = (patch) => setListState((current) => ({ ...current, page: 1, ...patch }));

  // A new search starts again on page 1; reopening the list keeps the page it was on.
  useEffect(() => {
    if (search !== listState.search) setListState((current) => ({ ...current, search, page: 1 }));
  }, [search, listState.search, setListState]);

  const list = useStudentPage(state, version);
  const rows = useMemo(() => {
    const now = new Date();
    return list.items.map((student) => ({ student, reasons: studentReasons(student, now), name: fullName(student.user_detail) }));
  }, [list.items]);
  useEffect(() => { onItems(list.items); }, [list.items, onItems]);

  const pages = pageCount(list.count, PAGE_SIZE);
  const counts = list.summary?.counts || {};
  const total = counts[state.status];
  // A page past the end (students left the filter, or Back to a page that is gone): go to the last one.
  useEffect(() => {
    if (list.loading || list.stale) return;
    const next = pageAfterLoad({ page: state.page, pageSize: PAGE_SIZE, count: list.count, status: list.status, error: list.error, total });
    if (next !== null) setListState((current) => ({ ...current, page: next }));
  }, [list.loading, list.stale, list.status, list.error, list.count, state.page, total, setListState]);
  const moving = Boolean(list.error) && pageAfterLoad({ page: state.page, pageSize: PAGE_SIZE, count: 0, status: list.status, error: list.error, total }) !== null;

  const filtered = Boolean(query.trim() || state.grade || state.country || state.status !== 'all');
  const from = list.count ? (state.page - 1) * PAGE_SIZE + 1 : 0;
  const to = Math.min(list.count, (state.page - 1) * PAGE_SIZE + list.items.length);

  function changeView(next) {
    setView(next);
    saveView(next);
  }

  function clearSearch() {
    flushSearch('');
    setQuery('');
  }

  function clearFilters() {
    clearSearch();
    setListState((current) => ({ ...STUDENT_LIST_DEFAULTS, ordering: current.ordering }));
  }

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function stopSelecting() {
    setSelecting(false);
    setSelected(new Set());
  }

  function refresh() {
    setVersion((value) => value + 1);
    reload();
  }

  const chips = [
    query.trim() && ['search', `“${query.trim()}”`, clearSearch],
    state.status !== 'all' && ['status', t(STATUS_PILLS.find(([key]) => key === state.status)?.[1] || ''), () => update({ status: 'all' })],
    state.grade && ['grade', gradeText(state.grade), () => update({ grade: '' })],
    state.country && ['country', t(state.country), () => update({ country: '' })],
  ].filter(Boolean);

  const shown = { rows, selecting, selected, toggle, onPreview: setPreview };

  return <div className="cx-page cx-students cs-page">
    <CxHead title={t("Students")} subtitle={t("Your students and what they need from you")}>
      {selecting && <button type="button" className="cx-btn" onClick={stopSelecting}>{t("Cancel")}</button>}
      <button type="button" className="cx-btn" disabled={selecting && !selected.size} onClick={() => (selecting ? setAssigning(true) : setSelecting(true))}>
        <Plus size={15} aria-hidden="true" />{selecting && selected.size ? tp('Assign task to {n} student|Assign task to {n} students', selected.size, { n: selected.size }) : t("Assign task to several")}
      </button>
      {/* "Add student" slot: the page's onAddStudent decides what adding a student means. */}
      {!readOnly && <span className="cs-add-slot"><button type="button" className="cx-btn primary" onClick={onAddStudent || (() => setAdding(true))}><UserPlus size={15} aria-hidden="true" />{t("Add student")}</button></span>}
    </CxHead>

    <CxPills label={t("Filter students")} active={state.status} onChange={(status) => update({ status })} items={STATUS_PILLS.map(([key, title]) => [key, title, counts[key]])} />

    <div className="cs-filters">
      <div className="cs-filter-row">
        <label className="cx-search cs-search">
          <Search size={16} aria-hidden="true" />
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search by name…")} aria-label={t("Search by name…")} autoComplete="off" />
        </label>
        <label className="cs-field"><span>{t("Grade")}</span>
          <select value={state.grade} onChange={(event) => update({ grade: event.target.value })}>
            <option value="">{t("Any grade")}</option>
            {FILTER_GRADES.map((grade) => <option key={grade} value={grade}>{gradeText(grade)}</option>)}
          </select>
        </label>
        <label className="cs-field"><span>{t("Target country")}</span>
          <select value={state.country} onChange={(event) => update({ country: event.target.value })}>
            <option value="">{t("Any country")}</option>
            {(list.summary?.countries || COUNTRIES).map((country) => <option key={country} value={country}>{t(country)}</option>)}
          </select>
        </label>
        <label className="cs-field"><span>{t("Sort by")}</span>
          <select value={state.ordering} onChange={(event) => update({ ordering: event.target.value })}>
            {SORTS.map(([key, title]) => <option key={key} value={key}>{t(title)}</option>)}
          </select>
        </label>
        <div className="cs-view" role="group" aria-label={t("View")}>
          <button type="button" aria-pressed={view === 'table'} onClick={() => changeView('table')}><Rows3 size={15} aria-hidden="true" />{t("Table")}</button>
          <button type="button" aria-pressed={view === 'cards'} onClick={() => changeView('cards')}><LayoutGrid size={15} aria-hidden="true" />{t("Cards")}</button>
        </div>
      </div>
      {chips.length > 0 && <div className="cs-filter-row cs-filter-foot">
        <div className="cs-chips">
          {chips.map(([key, text, remove]) => <button key={key} type="button" className="cs-chip" onClick={remove} aria-label={t('Remove filter: {name}', { name: text })}>{text}<X size={13} aria-hidden="true" /></button>)}
          {filtered && <button type="button" className="cx-btn cs-clear" onClick={clearFilters}>{t("Clear filters")}</button>}
        </div>
      </div>}
    </div>

    {list.error && !moving && <div className="alert error" role="alert">{list.error} <button type="button" className="cx-btn" onClick={() => setVersion((value) => value + 1)}>{t("Retry")}</button></div>}
    <div className="cs-results" aria-busy={list.loading}>
      {(list.loading || moving) && !list.items.length ? <PageSkeleton /> : rows.length
        ? (view === 'cards' ? <StudentCards {...shown} /> : <StudentTable {...shown} />)
        : !list.error && <div className="cx-card cs-empty">
          <p>{filtered ? t("No students match these filters.") : t("No students assigned to you yet.")}</p>
          {filtered && <button type="button" className="cx-btn" onClick={clearFilters}>{t("Clear filters")}</button>}
        </div>}
    </div>

    {list.count > 0 && <nav className="cs-pager" aria-label={t("Pages")}>
      <span role="status">{tp('Showing {from}–{to} of {n} student|Showing {from}–{to} of {n} students', list.count, { from, to, n: list.count })}</span>
      <div className="cs-pager-buttons">
        <button type="button" className="cx-btn" disabled={state.page <= 1 || list.loading} onClick={() => setListState((current) => ({ ...current, page: current.page - 1 }))}><ChevronLeft size={15} aria-hidden="true" />{t("Previous")}</button>
        <span>{t('Page {p} of {total}', { p: state.page, total: pages })}</span>
        <button type="button" className="cx-btn" disabled={state.page >= pages || list.loading} onClick={() => setListState((current) => ({ ...current, page: current.page + 1 }))}>{t("Next")}<ChevronRight size={15} aria-hidden="true" /></button>
      </div>
    </nav>}
    <p className="cx-footnote">{t("Click a student for a quick look; “Open student” shows their Student 360.")}</p>
    {!readOnly && <CxAccountActions>
      <button type="button" role="menuitem" onClick={() => setConnecting(true)}>{t("Connect students")}</button>
    </CxAccountActions>}

    {preview && <StudentQuickPanel user={user} student={preview} onClose={closePreview} onOpen={onOpen} onDirect={onDirect} />}
    {assigning && <BulkTaskForm studentIds={[...selected]} onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); stopSelecting(); refresh(); }} notify={notify} />}
    {!readOnly && adding && <StudentForm user={user} data={data} student={null} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); refresh(); }} notify={notify} />}
    {!readOnly && connecting && <StudentAssignmentModal user={user} data={data} onClose={() => setConnecting(false)} onSaved={() => { setConnecting(false); refresh(); }} notify={notify} />}
  </div>;
}

// -- Student 360 ---------------------------------------------------------------

// A count stays out of the tab until its section has loaded: "Tasks · 0" while
// the records are still on their way (or failed) reads as "no tasks".
const TABS = (student, records, letters) => [
  ['overview', 'Overview'],
  ['review', 'To review', student.to_review_total ?? 0],
  ['tasks', 'Tasks', records.tasks?.length],
  ['documents', 'Documents', records.documents?.length],
  ['essays', 'Essays', records.essays?.length],
  ['applications', 'Applications', records.applications?.length],
  ['letters', 'Recommendations', records.recommendations ? letters.length : undefined],
  ['meetings', 'Meetings'],
  ['notes', 'Private notes'],
];

// What is missing from a profile, in words ("personal story", "an activity").
function missingAnswer(key) {
  const words = {
    photo: t('a photo'), graduation_year: t('graduation year'), guardian: t('guardian contact'), school: t('school details'), gpa: t('GPA'),
    ielts: t('IELTS status'), sat: t('SAT status'), countries: t('target countries'), interests: t('interests'),
    story: t('personal story'), activities: t('an activity'), honors: t('an honor'),
  };
  return words[key] || key;
}

// The reasons the Overview card lists, most urgent first: [{ key, tone, tag, text, action, run }].
function needsYouRows({ student, records, remind, goTo }) {
  const today = localDateKey();
  const rows = [];
  (records.tasks || []).filter((task) => ['todo', 'in_progress', 'late'].includes(task.status) && task.due_date < today).slice(0, 2).forEach((task) => rows.push({
    key: `task-${task.id}`, tone: 'late', tag: t('Late'), text: t('{title} · due {date}', { title: task.title, date: dayMonthText(task.due_date) }), action: t('Remind'), run: () => remind({ topic: 'task', record: task.id }),
  }));
  (records.documents || []).filter((doc) => doc.status === 'required' || (['uploaded', 'reviewing'].includes(doc.status) && !hasSubmission('document', doc))).slice(0, 1).forEach((doc) => rows.push({
    key: `doc-${doc.id}`, tone: 'late', tag: t('Missing'), text: t('{title} not uploaded', { title: doc.title }), action: t('Remind'), run: () => remind({ topic: 'document', record: doc.id }),
  }));
  if (student.to_review_total > 0) rows.push({
    key: 'review', tone: 'warn', tag: t('To review'), text: tp('{n} item waiting for you|{n} items waiting for you', student.to_review_total, { n: student.to_review_total }), action: t('Review'), run: () => goTo('review'),
  });
  const missing = student.profile_readiness?.missing || [];
  if (missing.length) rows.push({
    key: 'profile', tone: 'quiet', tag: t('Profile'), text: t('Missing: {items}', { items: missing.slice(0, 3).map((item) => missingAnswer(item.key)).join(', ') }), action: t('Remind'), run: () => remind({ topic: 'profile' }),
  });
  return rows;
}

function ProgressItem({ title, percent, caption }) {
  return <div className="cx-progress-item">
    <div><span>{title}</span><b>{formatPercentLocale(percent || 0)}</b></div>
    <CxProgress value={percent} label={title} />
    <small>{caption}</small>
  </div>;
}

function TestScores({ student }) {
  const sections = ['ielts_listening', 'ielts_reading', 'ielts_writing', 'ielts_speaking'].map((key) => student[key]);
  const band = (value) => formatNumberLocale(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const ielts = student.ielts_score != null;
  const sat = student.sat_score != null;
  if (!ielts && !sat) return <p className="cx-empty">{t("No test scores yet.")}</p>;
  return <p className="cx-scores">
    {ielts && <span>IELTS <b>{band(student.ielts_score)}</b>{sections.every((value) => value != null) && ` (${t('L {a} · R {b} · W {c} · S {d}', { a: band(sections[0]), b: band(sections[1]), c: band(sections[2]), d: band(sections[3]) })})`}</span>}
    {sat && <span>SAT <b>{formatNumberLocale(student.sat_score, { useGrouping: false })}</b>{student.sat_superscore === true && ` ${t('superscore')}`}</span>}
  </p>;
}

function Overview({ student, records, meetings, name, notify, reload, goTo }) {
  const activity = usePagedList('activity', { filters: { student: student.id }, pageSize: 5 });
  const [busy, setBusy] = useState(false);
  const next = meetings[0];

  async function remind(payload) {
    setBusy(true);
    try {
      const result = await api.remindStudent(student.id, payload);
      notify(result.sent ? t('Reminder sent to {name}.', { name }) : t('{name} was reminded recently.', { name }));
      activity.reload();
      reload();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const rows = needsYouRows({ student, records, remind, goTo });
  const statuses = student.task_status_counts || {};
  const openTasks = (statuses.todo || 0) + (statuses.in_progress || 0) + (statuses.late || 0);
  const readiness = student.profile_readiness || { percent: 0, done: 0, total: 0 };

  return <>
    <div className="cx-overview">
      <CxCard title={t("Why {name} needs you", { name })}>
        <div className="cx-reason-list">
          {rows.map((row) => <div key={row.key} className="cx-reason-row">
            <CxTag tone={row.tone}>{row.tag}</CxTag>
            <span>{row.text}</span>
            <button type="button" className="cx-btn" disabled={busy} onClick={row.run}>{row.action}</button>
          </div>)}
          {!rows.length && <p className="cx-empty">{t("Nothing needs your attention right now.")}</p>}
        </div>
      </CxCard>
      <CxCard title={t("Progress")}>
        <div className="cx-progress-list">
          <ProgressItem title={t("Application readiness")} percent={student.progress_percent} caption={t('{done} of {total}: tasks, applications, documents, letters', { done: student.readiness_items_done ?? 0, total: student.readiness_items_total ?? 0 })} />
          <ProgressItem title={t("Tasks")} percent={student.task_progress_percent} caption={joinParts(t('{n} open', { n: openTasks }), student.tasks_overdue > 0 && t('{n} late', { n: student.tasks_overdue }))} />
          <ProgressItem title={t("Profile ready")} percent={readiness.percent} caption={t('{done} of {total} answers', { done: readiness.done, total: readiness.total })} />
        </div>
      </CxCard>
      <CxCard title={t("Recent activity")}>
        <div className="cx-activity">
          {activity.items.map((item) => {
            const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(item.created_at).setHours(0, 0, 0, 0)) / 86400000);
            return <div key={item.id}><span>{days < 7 ? relativeDayText(item.created_at) : dayMonthText(item.created_at)}</span><span>{activityText(item.action)}</span></div>;
          })}
          {activity.loaded && !activity.items.length && <p className="cx-empty">{t("No activity yet.")}</p>}
        </div>
      </CxCard>
    </div>
    <div className="cx-overview-foot">
      <CxCard title={t("Test scores")}><TestScores student={student} /></CxCard>
      <CxCard title={t("Next meeting")}>
        {next
          ? <p className="cx-next-meeting"><span>{joinParts(`${dayLabel(next.starts_at)} ${clockText(next.starts_at)}`, next.topic)}</span>{next.status === 'pending' ? <CxTag tone="warn">{t("Waiting for you")}</CxTag> : <CxTag tone="ok">{t("Confirmed")}</CxTag>}</p>
          : <p className="cx-empty">{t("No upcoming meetings.")}</p>}
      </CxCard>
    </div>
  </>;
}

// One record of a student's tab: a title, a line under it and a status tag.
function RecordRow({ title, meta, status, onClick, children }) {
  const inner = <>
    <span className="cx-row-copy"><b>{title}</b>{meta && <small>{meta}</small>}</span>
    {status && <CxTag tone={statusTone(status)} small>{label(status)}</CxTag>}
    {children}
    {onClick && <ChevronRight className="cx-row-go" size={16} aria-hidden="true" />}
  </>;
  return onClick
    ? <button type="button" className="cx-row" onClick={onClick}>{inner}</button>
    : <div className="cx-row cx-row-static">{inner}</div>;
}

// `count` undefined: the section has not loaded, so say so rather than "nothing yet".
function RecordCard({ title, empty, children, count, loading = false }) {
  return <CxCard title={title}>
    <div className="cx-list">
      {children}
      {count === undefined ? loading && <p className="cx-empty" role="status">{t("Loading…")}</p> : !count && <p className="cx-empty">{empty}</p>}
    </div>
  </CxCard>;
}

function useDocumentHistory(studentId, version) {
  const [state, setState] = useState({ studentId: null, byDocument: new Map(), error: '' });
  useEffect(() => {
    let active = true;
    api.page('activity', `?student=${encodeURIComponent(studentId)}&kind=document&cursor=&page_size=100`).then((payload) => {
      if (!active) return;
      const byDocument = new Map();
      for (const entry of payload?.results || []) {
        byDocument.set(entry.metadata.record, [...(byDocument.get(entry.metadata.record) || []), entry]);
      }
      setState({ studentId, byDocument, error: '' });
    }, (error) => {
      if (active) setState((previous) => ({ ...previous, studentId, error: error.message }));
    });
    return () => {active = false;};
  }, [studentId, version]);
  return state.studentId === studentId ? state : { byDocument: new Map(), error: '' };
}

const REVIEW_ENDPOINTS = ['tasks', 'documents', 'achievements'];
const DECISION_ACTIONS = { approved: /^Document approved: /, rejected: /^Document sent back: / };

function documentWhen(doc, history) {
  const pattern = DECISION_ACTIONS[doc.status];
  if (pattern) {
    const decision = history.find((entry) => pattern.test(entry.action));
    if (!decision) return '';
    return joinParts(doc.status === 'approved' ? tx`Approved ${dateText(decision.created_at)}` : tx`Sent back ${dateText(decision.created_at)}`, decision.actor_name);
  }
  if (!hasSubmission('document', doc)) return t("No file uploaded yet.");
  return '';
}

function StudentDocuments({ documents, loading, history, onOpen }) {
  return <RecordCard title={t("Documents")} count={documents?.length} loading={loading} empty={t("No documents yet.")}>
    {history.error && <p className="alert error" role="alert">{tx`Review history could not be loaded: ${history.error}`}</p>}
    {(documents || []).map((doc) => <RecordRow key={doc.id} title={doc.title} meta={joinParts(label(doc.document_type), documentWhen(doc, history.byDocument.get(doc.id) || []), doc.counselor_comment && `“${doc.counselor_comment}”`)} status={documentStatus(doc)} onClick={() => onOpen(doc)} />)}
  </RecordCard>;
}

function StudentNotes({ student, notify, onSaved }) {
  const [adding, setAdding] = useState(false);
  const notes = usePagedList('meetings', { filters: { student: student.id }, pageSize: 20 });
  return <CxCard title={t("Private notes")} action={<button type="button" className="cx-btn" onClick={() => setAdding(true)}><Plus size={15} aria-hidden="true" />{t("Add note")}</button>}>
    <div className="cx-list">
      {notes.items.map((note) => <RecordRow key={note.id} title={note.title} meta={joinParts(dateText(note.meeting_date), note.summary)} />)}
      {notes.loaded && !notes.items.length && <p className="cx-empty">{t("No private notes yet.")}</p>}
    </div>
    <LoadMore list={notes} />
    {adding && <MeetingNoteForm booking={{ student: student.id, topic: '', starts_at: localDateKey() }} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); notes.reload(); onSaved(); }} notify={notify} />}
  </CxCard>;
}

// A single student, as the "Counselor Dashboard" design's Student 360.
// A student's meetings, from the server (?student=): the workspace holds only
// the counselor's recent window. Upcoming ones (Overview) and the whole
// history (Meetings tab, newest first, a page at a time).
function useStudentMeetings(studentId, tab) {
  const today = localDateKey();
  const upcoming = usePagedList('bookings', { filters: { student: studentId, starts_from: today }, ordering: 'starts', pageSize: 10 });
  const history = usePagedList('bookings', { filters: { student: studentId }, ordering: '-starts', pageSize: 20, enabled: tab === 'meetings' });
  return { upcoming, history };
}

function Student360Header({ student, onBack, children }) {
  const name = fullName(student.user_detail);
  const readiness = student.profile_readiness || { percent: 0, missing: [] };
  const missing = readiness.missing || [];
  const meta = joinParts(gradeOrPending(student.grade), student.school_name, student.target_major, splitList(student.target_countries).map((country) => t(country)).join(', '));
  return <>
    <div className="cx-s360-top">
      <button type="button" className="cx-back" onClick={onBack}><ChevronLeft size={16} aria-hidden="true" /><b>{t('Students')}</b></button>
      <span className="cx-crumb">/ {name}</span>
      <div className="cx-s360-actions">{children}</div>
    </div>
    <section className="cx-hero">
      <span className="cx-hero-disc" aria-hidden="true">{initials(name)}</span>
      <div className="cx-hero-copy"><span>{t('STUDENT 360°')}</span><h1>{name}</h1><p>{meta}</p></div>
      <dl className="cx-hero-stats">
        <div><dt>{formatPercentLocale(student.progress_percent || 0)}</dt><dd>{t('Application readiness')}</dd><dd>{tp('{done} of {n} item finished|{done} of {n} items finished', student.readiness_items_total ?? 0, { done: student.readiness_items_done ?? 0, n: student.readiness_items_total ?? 0 })}</dd></div>
        <div><dt>{formatPercentLocale(readiness.percent)}</dt><dd>{t('Profile ready')}</dd><dd>{tp('{n} answer missing|{n} answers missing', missing.length, { n: missing.length })}</dd></div>
      </dl>
    </section>
  </>;
}

const ASSISTANT_STUDENT_TABS = [['overview', 'Overview'], ['tasks', 'Tasks'], ['documents', 'Documents'], ['applications', 'Applications'], ['portfolio', 'Portfolio']];
const ASSISTANT_PORTFOLIO = [['researches', 'Research'], ['projects', 'Projects'], ['internships', 'Internships'], ['activities', 'Activities'], ['honors', 'Honors'], ['achievements', 'Achievements']];

// Read-only Student 360 uses the counselor's header, tabs, progress and record cards.
// No counselor-only hooks (notes, essays, letters, meetings or activity) run here.
function AssistantStudent360({ student, user, onBack, onDirect, notify, reload, refreshStudent }) {
  const [tab, setTab] = useState('overview');
  const [task, setTask] = useState(null);
  const [document, setDocument] = useState(null);
  const [assigning, setAssigning] = useState(false);
  const loaded = useStudentRecords(student.id, true, studentRecordEndpoints(user));
  const { records } = loaded;
  const reasons = studentReasons(student, new Date());
  async function sendBack(note) {
    await api.sendBack('tasks', task.id, note);
    setTask(null);
    notify(t('Sent back to the student.'));
    loaded.reload(['tasks']);
    invalidatePagedLists(['tasks', 'students']);
    refreshStudent();
    reload();
  }
  return <div className="cx-page cx-student-360">
    <Student360Header student={student} onBack={onBack}>
      <button type="button" className="cx-btn" onClick={() => onDirect(student.user_detail?.id)}><MessageCircle size={15} aria-hidden="true" />{t('Message')}</button>
      <button type="button" className="cx-btn primary" onClick={() => setAssigning(true)}><Plus size={15} aria-hidden="true" />{t("Assign task")}</button>
    </Student360Header>
    <CxTabs items={ASSISTANT_STUDENT_TABS} active={tab} onChange={setTab} label={t('Student sections')} />
    {loaded.error && <div className="alert error" role="alert">{loaded.error}</div>}
    {tab === 'overview' && <>
      <div className="cx-overview">
        <CxCard title={t('What needs attention')}><div className="cx-progress-list">
          {reasons.length ? <ReasonTags reasons={reasons} /> : <p className="cx-empty">{t('Nothing needs your attention right now.')}</p>}
        </div></CxCard>
        <CxCard title={t('Progress')}><div className="cx-progress-list">
          <ProgressItem title={t('Application readiness')} percent={student.progress_percent} />
          <ProgressItem title={t('Tasks')} percent={student.task_progress_percent} />
          <ProgressItem title={t('Profile ready')} percent={student.profile_readiness?.percent} />
        </div></CxCard>
        <CxCard title={t('Test scores')}><TestScores student={student} /></CxCard>
      </div>
      <RecordCard title={t('Academic & planning')} count={1}>
        <RecordRow title={t('GPA')} meta={student.gpa == null ? t('Not provided') : formatNumberLocale(student.gpa)} />
        <RecordRow title={t('Target major')} meta={student.target_major || t('Not provided')} />
        <RecordRow title={t('Target countries')} meta={targetText(student) || t('Not provided')} />
        <RecordRow title={t('Counselor')} meta={student.counselor_name || t('Not provided')} />
      </RecordCard>
    </>}
    {tab === 'tasks' && <RecordCard title={t('Tasks')} count={records.tasks?.length} loading={loaded.loading} empty={t('No assigned tasks found.')}>
      {(records.tasks || []).map((item) => <RecordRow key={item.id} title={item.title} meta={item.due_date && tx`Due ${dateText(item.due_date)}`} status={item.status} onClick={() => setTask(item)} />)}
    </RecordCard>}
    {tab === 'documents' && <RecordCard title={t('Documents')} count={records.documents?.length} loading={loaded.loading} empty={t('No documents yet.')}>
      {(records.documents || []).map((item) => <RecordRow key={item.id} title={item.title} meta={label(item.document_type)} status={documentStatus(item)} onClick={() => setDocument(item)} />)}
    </RecordCard>}
    {tab === 'applications' && <RecordCard title={t('Applications')} count={records.applications?.length} loading={loaded.loading} empty={t('The student has not added any universities to the college list yet.')}>
      {(records.applications || []).map((item) => <RecordRow key={item.id} title={item.university_detail?.name || t('University')} meta={item.program} status={item.status} />)}
    </RecordCard>}
    {tab === 'portfolio' && <div className="section-stack">{ASSISTANT_PORTFOLIO.map(([resource, title]) => <RecordCard key={resource} title={t(title)} count={records[resource]?.length} loading={loaded.loading} empty={t('No information available yet.')}>
      {(records[resource] || []).map((item) => <RecordRow key={item.id} title={item.title || item.organization || item.name} meta={item.description} />)}
    </RecordCard>)}</div>}
    {task && <TaskSubmissionModal task={task} onClose={() => setTask(null)} notify={notify} onSendBack={task.status === 'submitted' ? sendBack : null} />}
    {document && <DocumentPreviewModal document={document} onClose={() => setDocument(null)} notify={notify} />}
    {assigning && <BulkTaskForm studentIds={[student.id]} onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); loaded.reload(['tasks']); invalidatePagedLists(['tasks', 'students']); }} notify={notify} />}
  </div>;
}

function CounselorStudent360({ student, user, data, onBack, onDirect, notify, reload: reloadWorkspace, setPage, refreshStudent }) {
  const [tab, setTab] = useState('overview');
  const [booking, setBooking] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [credential, setCredential] = useState(false);
  const [invite, setInvite] = useState(false);
  const [document, setDocument] = useState(null);
  const [task, setTask] = useState(null);
  const [noteFor, setNoteFor] = useState(null);
  const loaded = useStudentRecords(student.id, true, studentRecordEndpoints(user));
  const records = loaded.records;
  const [historyVersion, setHistoryVersion] = useState(0);
  // Only review decisions and level approvals change the workspace's stats and badges.
  // Without that reload, other pages' cached copies of the touched sections are dropped here.
  const reload = ({ endpoints = [], patch = null, workspace = false } = {}) => {
    if (endpoints.length) {
      loaded.reload(endpoints);
      invalidatePagedLists(endpoints);
    }
    if (endpoints.includes('documents')) setHistoryVersion((value) => value + 1);
    refreshStudent(patch);
    if (workspace) reloadWorkspace();
  };
  // Letters saved here show over the loaded list until a refresh brings them (or newer).
  const [savedLetters, setSavedLetters] = useState({ studentId: null, items: [] });
  const ownSaved = savedLetters.studentId === student.id ? savedLetters.items : [];
  const letters = mergeSaved(records.recommendations || [], ownSaved);
  const letterSaved = (saved) => {
    setSavedLetters({
      studentId: student.id,
      items: [saved, ...ownSaved.filter((item) => item.id !== saved.id)],
    });
    reload({ endpoints: ['recommendations'] });
  };
  const name = fullName(student.user_detail);
  const documentHistory = useDocumentHistory(student.id, historyVersion);
  // The open document is read from the loaded records, so a decision shows its new status.
  const openDocument = (records.documents || []).find((doc) => doc.id === document) || null;
  async function decideDocument(action, note) {
    if (action === 'sendBack') {
      await api.sendBack('documents', openDocument.id, note);
      notify(t("Sent back to the student."));
    } else {
      await api.approveRecord('documents', openDocument.id, note);
      notify(t("Document approved."));
    }
    setDocument(null);
    reload({ endpoints: ['documents'], workspace: true });
  }
  const studentMeetings = useStudentMeetings(student.id, tab);
  const meetings = studentMeetings.history.items;
  const upcoming = useMemo(() => upcomingMeetings(studentMeetings.upcoming.items), [studentMeetings.upcoming.items]);
  const now = new Date();
  const reviewItems = useMemo(() => {
    const named = (items) => items.map((item) => ({ ...item, student_name: item.student_name || name }));
    return mergeReviewQueue({
      tasks: named((records.tasks || []).filter((item) => item.status === 'submitted')),
      documents: named((records.documents || []).filter((item) => ['uploaded', 'reviewing'].includes(item.status) && hasSubmission('document', item))),
      achievements: named((records.achievements || []).filter((item) => !item.verified && !item.counselor_comment)),
    });
  }, [records, name]);
  const tabs = TABS(student, records, letters);

  return <div className="cx-page cx-student-360">
    <Student360Header student={student} onBack={onBack}>
        <DownloadCvButton studentId={student.id} className="cx-btn" notify={notify} />
        <button type="button" className="cx-btn" onClick={() => onDirect(student.user_detail?.id)}><MessageCircle size={15} aria-hidden="true" />{t("Message")}</button>
        <button type="button" className="cx-btn" onClick={() => setBooking(true)}><Calendar size={15} aria-hidden="true" />{t("Book meeting")}</button>
        <button type="button" className="cx-btn primary" onClick={() => setAssigning(true)}><Plus size={15} aria-hidden="true" />{t("Assign task")}</button>
    </Student360Header>

    <CxTabs items={tabs} active={tab} onChange={setTab} label={t("Student sections")} />
    {loaded.error && <div className="alert error" role="alert">{loaded.error}</div>}

    {tab === 'overview' && <>
      <Overview student={student} records={records} meetings={upcoming} name={student.user_detail?.first_name || name} notify={notify} reload={reload} goTo={setTab} />
    </>}
    <CxAccountActions>
      <button type="button" role="menuitem" onClick={() => setCredential(true)}>{t("Reset login")}</button>
      <button type="button" role="menuitem" onClick={() => setInvite(true)}>{t("Invite parent")}</button>
    </CxAccountActions>
    {tab === 'review' && <ReviewWorkspace items={reviewItems} loaded={!loaded.loading} notify={notify} reload={() => reload({ endpoints: REVIEW_ENDPOINTS, workspace: true })} setPage={setPage} studentLink={false} emptyText={t("Nothing from this student is waiting for review.")} />}
    {tab === 'tasks' && <div className="section-stack">
      <RecordCard title={t("Tasks")} count={records.tasks?.length} loading={loaded.loading} empty={t("No assigned tasks found.")}>
        {(records.tasks || []).map((item) => <RecordRow key={item.id} title={item.title} meta={joinParts(item.due_date && tx`Due ${dateText(item.due_date)}`, label(item.priority))} status={item.status === 'todo' && item.due_date < localDateKey() ? 'late' : item.status} onClick={() => setTask(item)} />)}
      </RecordCard>
    </div>}
    {tab === 'documents' && <StudentDocuments documents={records.documents} loading={loaded.loading} history={documentHistory} onOpen={(doc) => setDocument(doc.id)} />}
    {tab === 'essays' && <RecordCard title={t("Essays")} count={records.essays?.length} loading={loaded.loading} empty={t("This student hasn’t shared any essays yet.")}>
      {(records.essays || []).map((item) => <RecordRow key={item.id} title={item.title} meta={joinParts(tx`Version ${item.version}`, item.university_name || t("General essay"))} status={item.status} onClick={() => setPage('essays', { essayId: item.id })} />)}
    </RecordCard>}
    {tab === 'applications' && <RecordCard title={t("Applications")} count={records.applications?.length} loading={loaded.loading} empty={t("The student has not added any universities to the college list yet.")}>
      {(records.applications || []).map((item) => <RecordRow key={item.id} title={item.university_detail?.name || t("University")} meta={joinParts(item.program, label(item.tier), item.deadline && tx`Deadline: ${dateText(item.deadline)}`)} status={item.status} />)}
    </RecordCard>}
    {tab === 'letters' && <RecommendationLetters student={student} user={user} letters={letters} loading={loaded.loading} notify={notify} onSaved={letterSaved} />}
    {tab === 'meetings' && <RecordCard title={t("Meetings")} count={studentMeetings.history.loaded ? meetings.length : 1} empty={t("No meetings scheduled.")}>
      {meetings.map((item) => <RecordRow key={item.id} title={item.topic} meta={joinParts(dateTimeText(item.starts_at), item.duration_minutes > 0 && tx`${item.duration_minutes} min`)} status={meetingBadgeStatus(meetingStatus(item, now, { student: false }))}>
        <button type="button" className="cx-btn" onClick={() => setNoteFor(item)}>{t("Notes")}</button>
      </RecordRow>)}
      <PagedListError list={studentMeetings.history} />
      <LoadMore list={studentMeetings.history} />
    </RecordCard>}
    {tab === 'notes' && <StudentNotes student={student} notify={notify} onSaved={() => reload()} />}

    {booking && <BookingForm staff defaultStudentId={student.id} onClose={() => setBooking(false)} onSaved={() => { setBooking(false); invalidatePagedLists(['bookings']); reload(); }} notify={notify} />}
    {assigning && <BulkTaskForm studentIds={[student.id]} onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); reload({ endpoints: ['tasks'] }); }} notify={notify} />}
    {credential && <TemporaryCredentialModal account={student.user_detail} onClose={() => setCredential(false)} notify={notify} />}
    {invite && <ParentInviteModal student={student} onClose={() => setInvite(false)} notify={notify} />}
    {openDocument && <DocumentPreviewModal document={openDocument} history={documentHistory.error ? null : documentHistory.byDocument.get(openDocument.id) || []} onDecide={decideDocument} onClose={() => setDocument(null)} notify={notify} />}
    {task && <TaskSubmissionModal task={task} onClose={() => setTask(null)} notify={notify} />}
    {noteFor && <MeetingNoteForm booking={noteFor} onClose={() => setNoteFor(null)} onSaved={() => { setNoteFor(null); invalidatePagedLists(['meetings', 'bookings']); reload(); }} notify={notify} />}
  </div>;
}

// The counselor's Students page: the list, or one student's 360 when the URL names one
// (/students/15), so a reload, a bookmark or Back reopens the same profile. The list's
// filters and page live here, so Back from a profile returns to the same view.
// `onAddStudent` replaces the header's "Add student" (default: the quick-create form).
export function CounselorStudentsPage({ user, data, query, setQuery, reload, notify, studentId = null, onStudent, onDirect, setPage, onAddStudent }) {
  const [listState, setListState] = useState(() => ({ ...STUDENT_LIST_DEFAULTS, search: query }));
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const listed = useRef([]);
  const onItems = useCallback((items) => { listed.current = items; }, []);
  // Opening student B while A's record is still loading must never show A's.
  const request = useRef(createLatestRequest()).current;
  useEffect(() => {
    setError('');
    if (!studentId) {
      request.cancel();
      setSelected(null);
      return;
    }
    const isCurrent = request.start();
    setSelected(listed.current.find((item) => item.id === studentId) || null);
    api.retrieve('students', studentId).then(
      (student) => { if (isCurrent()) setSelected(student); },
      (failure) => { if (isCurrent()) setError(failure.status === 404 ? t("Student profile not found.") : failure.message); },
    );
  }, [studentId, request, attempt]);

  // After an action in the 360: show what is already known (`patch`), then the
  // server's row (to-review total, level, readiness). A failed refresh keeps the profile open.
  function refreshStudent(patch = null) {
    if (!studentId) return;
    if (patch) setSelected((current) => (current?.id === studentId ? { ...current, ...patch } : current));
    const isCurrent = request.start();
    api.retrieve('students', studentId).then(
      (student) => { if (isCurrent()) setSelected(student); },
      (failure) => { if (isCurrent()) notify(failure.message, 'error'); },
    );
  }

  if (studentId && error) return <div className="cx-page"><button type="button" className="cx-back" onClick={() => onStudent(null)}><ChevronLeft size={16} aria-hidden="true" /><b>{t("Students")}</b></button><div className="alert error" role="alert">{error} <button type="button" className="cx-btn" onClick={() => setAttempt((n) => n + 1)}>{t("Retry")}</button></div></div>;
  if (studentId && selected?.id !== studentId) return <PageSkeleton />;
  if (studentId && user.role === 'assistant') return <AssistantStudent360 student={selected} {...{ user, onDirect, notify, reload, refreshStudent }} onBack={() => onStudent(null)} />;
  if (studentId) return <CounselorStudent360 student={selected} {...{ user, data, onDirect, notify, reload, setPage, refreshStudent }} onBack={() => onStudent(null)} />;
  return <CounselorStudentList {...{ user, data, query, setQuery, listState, setListState, onItems, onDirect, onAddStudent, notify, reload }} onOpen={(student) => onStudent(student.id)} />;
}
